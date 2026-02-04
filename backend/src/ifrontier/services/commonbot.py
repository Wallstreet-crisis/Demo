from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from ifrontier.domain.assets.profile import get_profile
from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.payloads import (
    AiCommonBotDecisionPayload,
    TradeIntentSubmittedPayload,
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.llm.openrouter import OpenRouterClient, extract_first_message_text


def _price_trend(price_series: List[float]) -> float:
    if len(price_series) < 2:
        return 0.0
    return (price_series[-1] - price_series[0]) / max(price_series[0], 1e-6)


def _score_decision(
    visual_truth: str,
    symbol: str,
    price_series: List[float],
    news_text: str | None = None,
) -> Tuple[str, float]:
    profile = get_profile(symbol)
    sector = profile.sector if profile else "GENERIC"

    base = 0.0
    vt_upper = visual_truth.upper()
    if vt_upper == "PROFIT":
        base = 0.7
    elif vt_upper == "LOSS":
        base = -0.7
    
    # 增加对新闻文本的简单启发式扫描 (散户机器人逻辑)
    text_impact = 0.0
    if news_text:
        text_upper = news_text.upper()
        # 战争/危机关键词 (支持中英文)
        war_keywords = [
            "WAR", "CONFLICT", "CRISIS", "BATTLE", "MILITARY", "INVASION", "STRIKE", "GLOBAL WAR", "WORLD WAR",
            "战争", "冲突", "危机", "战役", "军事", "入侵", "打击", "全球战争", "世界大战", "不可抗力", "停产"
        ]
        if any(k in text_upper for k in war_keywords):
            # 军工和能源股看涨，金融/消费/技术/物流看跌
            if sector in ["MILITARY", "ENERGY"]:
                text_impact += 0.8  # 强烈看涨
            elif sector in ["FINANCE", "CONSUMER", "TECH", "LOGISTICS", "HEALTHCARE"]:
                text_impact -= 0.7  # 强烈看跌
            else:
                text_impact -= 0.3 # 整体不确定性
        
        # 增长关键词 (支持中英文)
        growth_keywords = [
            "GROWTH", "BOOM", "SUCCESS", "RECOVERY", "PROFIT", "ACQUISITION", "DIVIDEND", "BREAKTHROUGH",
            "增长", "繁荣", "成功", "复苏", "盈利", "收购", "分红", "派息", "突破", "利好"
        ]
        if any(k in text_upper for k in growth_keywords):
            text_impact += 0.4
            
        # 负面/调查关键词 (支持中英文)
        negative_keywords = [
            "INVESTIGATION", "LAWSUIT", "LEAK", "SUSPEND", "LOSS", "STOP", "REGULATION",
            "调查", "诉讼", "泄露", "暂停", "亏损", "停止", "管制", "合规", "禁令"
        ]
        if any(k in text_upper for k in negative_keywords):
            text_impact -= 0.4
            
    sector_adj = 0.0
    if sector == "MILITARY":
        sector_adj = 0.15
    elif sector == "ENERGY":
        sector_adj = 0.1
    elif sector == "FINANCE":
        sector_adj = -0.1

    trend = _price_trend(price_series)
    trend_adj = 0.0
    if trend > 0.05:
        trend_adj = -0.1
    elif trend < -0.05:
        trend_adj = 0.1

    score = max(min(base + text_impact + sector_adj + trend_adj, 1.0), -1.0)

    if score > 0.3:
        action = "BUY"
    elif score < -0.3:
        action = "SELL"
    else:
        action = "HOLD"

    return action, score


def run_commonbot_for_earnings(
    *,
    symbol: str,
    visual_truth: str,
    price_series: List[float],
    bot_id: str,
    correlation_id,
    news_text: str | None = None,
    use_llm: bool = False,
    truth_payload: Dict[str, Any] | None = None,
    is_insider: bool = False,
    author_id: str = "system",
    mutation_depth: int = 0,
) -> Tuple[EventEnvelopeJson, EventEnvelopeJson | None]:
    llm_result = None
    
    # --- 核心博弈逻辑：真理与欺骗 ---
    # 规则：
    # 1. 只有“系统发布的事实新闻”（如正式公告、已决大事件）且未被玩家篡改（author_id == 'system'）才值得 100% 信任。
    # 2. 如果作者不是 system，或者是传闻类（RUMOR, LEAK, OMEN），机器人必须像人类玩家一样分析文本。
    # 3. 玩家伪造的文本如果足够逼真，就能愚弄机器人做出错误操作。
    # 4. “内幕机器人”（Institutional Bots）有更高概率穿透伪装，但也可能被带节奏。
    
    news_kind = str((truth_payload or {}).get("kind") or "UNKNOWN").upper()
    is_system_fact = (author_id == "system") and (news_kind in ["MAJOR_EVENT", "WORLD_EVENT", "EARNINGS"]) and (not news_kind.startswith("OMEN"))
    
    # 决定是否参考“真相”
    # 只有系统原生事实，或者具有内幕背景的机器人在特定情况下才看 truth_payload
    should_trust_truth = is_system_fact or is_insider
    
    # 如果作者不是系统，或者新闻属于传闻性质，强制进入博弈模式
    if author_id != "system" or news_kind in ["RUMOR", "LEAK", "OMEN"]:
        # 即使是内幕机器人，面对谣言也有 30% 概率被带节奏，如果是经过多次传播（失真）则概率更高
        mislead_chance = 0.3 + (min(mutation_depth, 5) * 0.1)
        if is_insider and random.random() < mislead_chance:
            should_trust_truth = False
            mode_desc = f"INSIDER_MISLED (Chance: {mislead_chance:.0%})"
        else:
            # 普通机器人面对谣言/非系统新闻必须通过分析文本来决策
            should_trust_truth = False if not is_insider else True
            mode_desc = "INSIDER_PENETRATION" if should_trust_truth else "RETAIL_SPECULATION (Focus text)"
    else:
        mode_desc = "FACT_TRUST" if should_trust_truth else "TEXT_ANALYSIS"

    print(f"[Bot:Decision] {bot_id} for {symbol}: Mode={mode_desc}, Kind={news_kind}, Author={author_id}, Depth={mutation_depth}")

    is_rumor = (author_id != "system") or (news_kind in ["RUMOR", "LEAK", "OMEN"])

    if should_trust_truth and truth_payload:
        # 1) 穿透模式：直接读取真相
        direction = truth_payload.get("direction")
        if not direction and truth_payload.get("impact_map"):
            direction = truth_payload["impact_map"].get(symbol)
            
        if direction:
            direction = str(direction).upper()
            if direction == "UP":
                action, score = "BUY", 0.95
            elif direction == "DOWN":
                action, score = "SELL", 0.95
            else:
                action, score = "HOLD", 0.1
            confidence = score
            w_visual, w_text, w_trend = 0.05, 0.05, 0.9 
        elif use_llm:
            llm_result = _llm_decide_from_news(
                symbol=symbol,
                visual_truth=visual_truth,
                news_text=news_text or "",
                price_series=price_series,
                is_rumor=is_rumor,
            )
    else:
        # 2) 博弈模式：分析可能被伪造的文本
        # 这也是玩家发挥的空间：通过病毒式传播伪造利好/利空文字来收割机器人
        if use_llm:
            llm_result = _llm_decide_from_news(
                symbol=symbol,
                visual_truth=visual_truth,
                news_text=news_text or "",
                price_series=price_series,
                is_rumor=is_rumor,
            )

    if llm_result is not None:
        action = str(llm_result.get("action") or "HOLD").upper()
        confidence = float(llm_result.get("confidence") or 0.0)
        w_visual = float(llm_result.get("w_visual") or 0.0)
        w_text = float(llm_result.get("w_text") or 0.0)
        w_trend = float(llm_result.get("w_trend") or 0.0)
    else:
        action, score = _score_decision(visual_truth, symbol, price_series, news_text=news_text)
        confidence = abs(float(score))
        w_visual, w_text, w_trend = 0.3, 0.7, 0.0

    now = datetime.now(timezone.utc)

    decision_payload = AiCommonBotDecisionPayload(
        bot_id=bot_id,
        tick_id="debug-tick",
        asset_symbol=symbol,
        action=action,
        confidence=confidence,
        w_visual=w_visual,
        w_text=w_text,
        w_trend=w_trend,
        decided_at=now,
    )

    decision_envelope = EventEnvelope[AiCommonBotDecisionPayload](
        event_type=EventType.AI_COMMONBOT_DECISION,
        correlation_id=correlation_id,
        actor=EventActor(agent_id=bot_id),
        payload=decision_payload,
    )

    decision_json = EventEnvelopeJson.from_envelope(decision_envelope)

    trade_json: EventEnvelopeJson | None = None
    if action in {"BUY", "SELL"}:
        # 增加交易规模：不再是固定的 1.0 股
        # 根据信心指数和机器人类型分配规模
        # 散户机器人通常 10-100 股，机构机器人（inst）通常 1000-10000 股
        base_size = 10.0
        if "inst" in bot_id:
            base_size = 1000.0
        
        # 随信心指数指数级增长
        size = base_size * (2 ** (confidence * 3))
        # 增加一些随机性
        import random
        size *= random.uniform(0.8, 1.2)

        intent_payload = TradeIntentSubmittedPayload(
            intent_id=str(uuid4()),
            user_id="commonbot:" + bot_id,
            symbol=symbol,
            side=action,
            size=float(round(size, 2)),
            price_hint=price_series[-1] if price_series else None,
            confidence=confidence, # v0.2: 直接传入信心指数
            created_at=now,
        )

        intent_envelope = EventEnvelope[TradeIntentSubmittedPayload](
            event_type=EventType.TRADE_INTENT_SUBMITTED,
            correlation_id=correlation_id,
            actor=EventActor(agent_id=bot_id),
            payload=intent_payload,
        )
        trade_json = EventEnvelopeJson.from_envelope(intent_envelope)

    return decision_json, trade_json


def _llm_decide_from_news(
    *,
    symbol: str,
    visual_truth: str,
    news_text: str,
    price_series: List[float],
    is_rumor: bool = False,
) -> Dict[str, Any] | None:
    client = OpenRouterClient.from_env()
    if client is None:
        return None

    trend = _price_trend(price_series)

    # 针对谣言/传闻类新闻，调整系统提示词，使其更关注“市场情绪”和“文字诱导”
    if is_rumor:
        system = (
            "你是一个在极端金融危机中博弈的非专业散户(retail bot)。你很容易被社交媒体上的传闻和泄密煽动。"
            "你只能输出 JSON，不要输出其它文字。"
            "现在的市场充满了各种真假难辨的传闻(RUMOR/LEAK)。你无法看到所谓的‘后台真相’，你只能看到这些文字描述。"
            "如果文字描述看起来非常劲爆或具有毁灭性，即使它可能只是一个谣言，你也会倾向于跟风操作，以此收割利润或避免归零。"
            "action 只能是 BUY/SELL/HOLD。confidence 在 0~1 之间。请给出你的博弈权重 w_visual/w_text/w_trend。"
        )
    else:
        system = (
            "你是一个在极端金融危机中博弈的市场参与者(common bot)。你的目标是极度贪婪或极度恐惧。不要平庸。"
            "你只能输出 JSON，不要输出其它文字。"
            "根据新闻的视觉真相、文本、以及价格趋势，生成极具攻击性的交易动作。"
            "action 只能是 BUY/SELL/HOLD。confidence 在 0~1 之间。"
            "如果你看到战争、冲突、危机等词汇，且涉及的是军工股，你应该狂热买入；如果是消费或金融，你应该恐慌性抛售。"
            "同时给出权重 w_visual/w_text/w_trend（0~1）。"
        )

    user = (
        "请输出 JSON："
        "{\"action\":\"BUY|SELL|HOLD\",\"confidence\":0.0,"
        "\"w_visual\":0.0,\"w_text\":0.0,\"w_trend\":0.0}.\n"
        f"symbol: {symbol}\n"
        f"visual_truth: {visual_truth}\n"
        f"news_text: {news_text}\n"
        f"price_trend: {trend}\n"
    )

    # v0.2: 增加 max_tokens 防止 JSON 被截断，提升稳定性
    resp = client.chat_completions(system=system, user=user, temperature=0.2, max_tokens=512)
    if not resp or "choices" not in resp:
        print(f"[LLM:CommonBot] LLM Request failed for {symbol}, falling back to heuristics.")
        return None

    text = extract_first_message_text(resp)
    # v0.2: 使用更鲁棒的 JSON 提取方法，解决 Markdown 代码块或 LLM 废话干扰
    clean_text = text.strip()
    try:
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}")
        if start_idx != -1 and end_idx != -1:
            clean_text = clean_text[start_idx : end_idx + 1]
        
        obj = __import__("json").loads(clean_text)
    except Exception as e:
        print(f"[LLM:CommonBot] JSON parse error for {symbol}: {e}. Text: {text[:200]}. Falling back to heuristics.")
        return None

    if not isinstance(obj, dict):
        return None
    return obj
