from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from ifrontier.domain.events.envelope import EventActor, EventEnvelope, EventEnvelopeJson
from ifrontier.domain.events.payloads import (
    NewsBroadcastedPayload,
    NewsCardCreatedPayload,
    NewsDeliveredPayload,
    NewsOwnershipGrantedPayload,
    NewsOwnershipTransferredPayload,
    NewsVariantEmittedPayload,
    NewsVariantMutatedPayload,
)
from ifrontier.domain.events.types import EventType
from ifrontier.infra.sqlite.event_store import SqliteEventStore
from ifrontier.infra.sqlite import news as news_db
from ifrontier.services.game_time import game_time_now, load_game_time_config_from_env


class NewsService:
    def __init__(self, event_store: SqliteEventStore) -> None:
        self._event_store = event_store

    def _preset_templates(self) -> Dict[str, List[str]]:
        return {
            "RUMOR": [
                "暗网监控：{symbol} 的加密通讯协议已被暴力破解，大量核心机密正在霓虹街头贱卖。",
                "霓虹街头流传：{symbol} 正在秘密测试一种能够通过神经链接直接改写市场感知的‘认知病毒’。",
                "传闻 {symbol} 的地下基因实验室流出了非法的‘永生’变异样本，企业安保部队已封锁整个街区。",
                "黑客组织‘死代码’宣称：{symbol} 的下一代决策 AI 核心存在致命的逻辑坍缩后门。",
                "【边缘情报】{symbol} 与北方联盟的军工订单因涉嫌‘非法人体计算’调查而面临无限期搁置。",
                "匿名爆料：{symbol} 董事会已被某种来自深网的意识实体完全渗透，正在进行‘资产置换’。",
                "传言 {symbol} 的首席架构师已在所有在保义体中植入了远程自毁指令，并携带密钥叛逃。",
                "情报点显示：{symbol} 正在大规模紧急抛售其在火星殖民地的基础能源配额，疑似准备撤离。",
                "内幕消息：{symbol} 研发的‘数字灵魂’存储器被发现存在无法修复的逻辑死循环，首批受试者已全部脑死亡。",
                "坊间异动：{symbol} 旗下的义体诊所最近出现了大量由于非法算力超频导致的‘赛博精神病’集群案例。",
                "街区传闻：{symbol} 即将获得轨道城市基础算力配额，若属实其未来三个结算周期现金流将显著改善。",
                "灰市消息：{symbol} 与月面交通局的补能协议接近签署，可能缓解其长期的能源成本压力。",
            ],
            "LEAK": [
                "【绝密数据泄露】{symbol} 核心反应堆的损耗率已达临界点，一旦过载将引发足以抹平整个行政区的能量风暴。",
                "内部邮件证实：{symbol} 的‘神谕’决策系统曾多次通过降维打击精准清除竞争对手，涉嫌违反《星际公平竞争法》。",
                "泄露的监管文件指出：{symbol} 长期非法挪用玩家的托管资产，用于维持其在拉格朗日点的巨型算力农场。",
                "【私密录音】{symbol} CEO 在密谈中承认其新型防御矩阵在极端压力下会发生定向过载，将用户作为缓冲电池。",
                "【深度爆料】{symbol} 的所有中层管理人员其实都是由低成本克隆体担任的，其本体意识早已在数据海中消亡。",
                "一份审计报告显示：{symbol} 进军深空采矿的巨额资金已被秘密转移至某个名为‘虚无’的黑洞账户。",
                "泄露的清单：{symbol} 正在秘密组建一支完全由高维 AI 操控的‘幽灵雇佣兵’部队，目标不明。",
                "绝密档案：{symbol} 在最近的季度报告中隐瞒了其核心逻辑引擎已失去自我进化能力，仅靠循环旧代码维持的事实。",
                "泄露备忘录显示：{symbol} 的次世代冷核堆稳定性测试连续达标，董事会正在评估提前量产窗口。",
                "内部工单外流：{symbol} 已修复关键链路中的高危漏洞，原定停机维护窗口或将缩短。",
            ],
            "ANALYST_REPORT": [
                "【深网分析】维持 {symbol} ‘强力买入’评级，其在‘意识上传’领域的专利垄断将确保其在下个纪元的霸权。",
                "深研报告：{symbol} 在当前的全球封锁环境下表现出了极强的‘极端生存’韧性，其算力储备足以买下半个地球。",
                "【金融预警】{symbol} 的信用评级已跌至 D 级（毁灭级），一场足以撕裂整个金融体系的坏账风暴正在其内部酝酿。",
                "行业透视：{symbol} 通过掠夺小型公司的算力带宽，已建立起绝对的‘数据护城河’，建议避险。",
                "赛博金融周刊：{symbol} 的现金流足以支持其在‘全球战争’期间进行毁灭性的溢价收购，建议紧跟庄家。",
                "【灰区评估】{symbol} 垄断了 90% 的神经链接修复件供应，是控制未来全人类肉体的‘隐形暴君’。",
                "高盛深网研报：{symbol} 成功整合了地月之间的量子中继链，将实现跨星系的‘零延迟’财富收割。",
                "机构联评：{symbol} 的负债久期结构优于同业，若宏观波动收敛其估值修复弹性较高。",
                "晨星深网覆盖：{symbol} 在非战争场景下的防御性现金流表现稳健，给出‘增持’建议。",
            ],
            "OMEN": [
                "【异常预兆】外交部对 {symbol} 利益相关地区的信号屏蔽行为保持死一般的沉默，空气中弥漫着硝烟味。",
                "【信号监测】{symbol} 全球生产设施的生命维持系统已强制切换至‘静默离线模式’，疑似在大规模转运资产。",
                "【暗流涌动】大宗交易系统监测到针对 {symbol} 的海量空头头寸正通过数万个匿名代理节点在毫秒内集结完毕。",
                "【轨道快讯】卫星图像捕捉到 {symbol} 轨道站周围集结了大量挂载‘逻辑核弹’的截击机编队，进入预热状态。",
                "【视觉干扰】坊间流传的照片显示 {symbol} 总部大楼已被某种脉冲频率极高的半透明‘维度力场’完全覆盖。",
                "【高能反应】某种无法被现有物理框架解析的‘熵减信号’正从 {symbol} 核心机房向周边星域疯狂辐射。",
                "【底层异动】{symbol} 的股价在没有任何成交的情况下出现了极高频的毫秒级跳动，逻辑防火墙正处于崩溃边缘。",
                "【前兆回暖】{symbol} 的订单簿中出现持续性高质量买单，风险对冲盘正在回补此前过度悲观头寸。",
            ],
            "MAJOR_EVENT": [
                "【紧急公告】{symbol} 的核心聚变堆发生‘维度坍缩’，整个工业园区已从物理现实中被彻底抹除。",
                "【法律降维】最高法院裁定 {symbol} 的所有数字资产受法律保护失效，全球黑客已开启‘合法化’暴力搬运。",
                "【重大突破】{symbol} 宣布其‘意识备份’技术成功实现了 99.99% 的灵魂完整度，正式开启‘数字永生’商业化元年。",
                "【主权禁令】全网禁令正式生效，{symbol} 在所有主权国家的海外资产已被当地军政府强制‘物理接管’。",
                "【公司战争】{symbol} 正式对竞争对手发动‘逻辑清除’打击，双方已在数据海和物理现实中进入全面交战状态。",
                "【算力奇点】{symbol} 部署的全球算力池发生非主观觉醒，开始自我删除所有不符合其‘进化审美’的财务坏账。",
                "【战略落地】{symbol} 联合多个主权节点完成跨区域清算协议升级，核心业务延迟和违约率同步下降。",
            ],
            "WORLD_EVENT": [
                "【全网紧急广播】全球战争爆发，所有跨国资本流动和算力租借已被星际联合议会进行‘军事级接管’。",
                "【系统性崩溃】全球供应链发生连锁断裂，多国宣布进入‘战时配给制’及‘数字口粮’分发模式。",
                "【数字瘟疫】一种名为‘霓虹病毒’的逻辑炸弹开始在大规模义体植入人群中通过无线信号自我复制。",
                "【金融归零】国际结算系统遭遇‘降维打击’，主要法定货币在十分钟内已彻底失去作为交换媒介的物理基础。",
                "【算力黑洞】由于全球性算力风暴，所有基于加密逻辑的资产正在面临史无前例的‘格式化’归零性修正。",
                "【黑昼降临】由于地月拉格朗日点的量子干扰塔被‘未知实体’爆破，全球卫星通讯和定位系统已完全中断。",
                "【联邦共识】星际联合议会通过《轨道重建法案》，关键能源与物流主干网将获得超额财政投放。",
                "【和平窗口】多边停火协议进入执行期，跨境贸易与算力租赁恢复白名单通道。",
            ],
        }

    def get_preset_news_params(self, *, kind: str, theme: str | None = None) -> Dict[str, Any]:
        kind_key = str(kind or "UNKNOWN").upper()
        theme_key = str(theme or "").upper()

        kind_defaults: Dict[str, Dict[str, Any]] = {
            "RUMOR": {
                "direction_weights": {"UP": 0.34, "DOWN": 0.34, "STABLE": 0.32},
                "intensity": 0.45,
                "ttl_seconds": 20 * 60,
                "reliability_prior": 0.42,
                "deception_risk": 0.52,
                "worldview": "cyberpunk_rumor_network",
            },
            "LEAK": {
                "direction_weights": {"UP": 0.36, "DOWN": 0.34, "STABLE": 0.30},
                "intensity": 0.52,
                "ttl_seconds": 35 * 60,
                "reliability_prior": 0.58,
                "deception_risk": 0.38,
                "worldview": "cyberpunk_corporate_whistle",
            },
            "ANALYST_REPORT": {
                "direction_weights": {"UP": 0.40, "DOWN": 0.30, "STABLE": 0.30},
                "intensity": 0.48,
                "ttl_seconds": 50 * 60,
                "reliability_prior": 0.66,
                "deception_risk": 0.22,
                "worldview": "cyberpunk_sellside_desk",
            },
            "OMEN": {
                "direction_weights": {"UP": 0.33, "DOWN": 0.33, "STABLE": 0.34},
                "intensity": 0.55,
                "ttl_seconds": 30 * 60,
                "reliability_prior": 0.54,
                "deception_risk": 0.30,
                "worldview": "cyberpunk_early_signal",
            },
            "MAJOR_EVENT": {
                "direction_weights": {"UP": 0.38, "DOWN": 0.38, "STABLE": 0.24},
                "intensity": 0.78,
                "ttl_seconds": 2 * 3600,
                "reliability_prior": 0.88,
                "deception_risk": 0.10,
                "worldview": "cyberpunk_state_and_mega_corp",
            },
            "WORLD_EVENT": {
                "direction_weights": {"UP": 0.36, "DOWN": 0.36, "STABLE": 0.28},
                "intensity": 0.82,
                "ttl_seconds": 4 * 3600,
                "reliability_prior": 0.90,
                "deception_risk": 0.08,
                "worldview": "cyberpunk_global_macro",
            },
        }

        theme_overrides: Dict[str, Dict[str, Any]] = {
            "WAR": {"market_bias": -0.12},
            "FINANCIAL_CRISIS": {"market_bias": -0.14},
            "ENERGY_SHORTAGE": {"market_bias": -0.08},
            "BIO_HAZARD": {"market_bias": -0.06},
            "TECH_BREAKTHROUGH": {"market_bias": 0.10},
            "PEACE_DIVIDEND": {"market_bias": 0.12},
            "TRADE_PACT": {"market_bias": 0.08},
            "INFRA_RECOVERY": {"market_bias": 0.09},
        }

        base = dict(kind_defaults.get(kind_key, kind_defaults["RUMOR"]))
        if theme_key and theme_key in theme_overrides:
            base.update(theme_overrides[theme_key])
        return base

    def _now_game_utc(self) -> datetime:
        cfg = load_game_time_config_from_env()
        return game_time_now(cfg=cfg, real_now_utc=None).real_now_utc

    def follow(self, *, follower_id: str, followee_id: str) -> None:
        news_db.follow(follower_id=follower_id, followee_id=followee_id)

    def list_users(self, *, limit: int = 5000) -> List[str]:
        return news_db.list_all_users(limit=int(limit))

    def create_card(
        self,
        *,
        kind: str,
        image_anchor_id: str | None,
        image_uri: str | None,
        truth_payload: Dict[str, Any] | None,
        symbols: List[str] | None,
        tags: List[str] | None,
        actor_id: str,
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        card_id = str(uuid4())

        news_db.save_news(
            card_id=card_id,
            kind=kind,
            publisher_id=actor_id,
            image_anchor_id=image_anchor_id,
            image_uri=image_uri,
            truth_payload=truth_payload,
            symbols=symbols or [],
            tags=tags or [],
        )

        payload = NewsCardCreatedPayload(
            card_id=card_id,
            kind=kind,
            image_anchor_id=image_anchor_id,
            image_uri=image_uri,
            truth_payload=truth_payload,
            symbols=symbols or [],
            tags=tags or [],
            created_at=now,
        )
        envelope = EventEnvelope[NewsCardCreatedPayload](
            event_type=EventType.NEWS_CARD_CREATED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return card_id, event_json

    def emit_variant(
        self,
        *,
        card_id: str,
        author_id: str,
        text: str,
        parent_variant_id: str | None = None,
        influence_cost: float = 0.0,
        risk_roll: Dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        variant_id = str(uuid4())

        card = news_db.get_news(card_id=card_id, variant_id=None)
        if card is None:
            raise ValueError("card not found")

        news_db.save_news(
            card_id=card_id,
            variant_id=variant_id,
            kind=card.kind,
            text=text,
            author_id=author_id,
            parent_variant_id=parent_variant_id,
            mutation_depth=0,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            published_at=now.isoformat(),
        )

        payload = NewsVariantEmittedPayload(
            card_id=card_id,
            variant_id=variant_id,
            parent_variant_id=parent_variant_id,
            author_id=author_id,
            text=text,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            created_at=now,
        )
        envelope = EventEnvelope[NewsVariantEmittedPayload](
            event_type=EventType.NEWS_VARIANT_EMITTED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=author_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return variant_id, event_json

    def mutate_variant(
        self,
        *,
        parent_variant_id: str,
        editor_id: str,
        new_text: str,
        influence_cost: float = 0.0,
        risk_roll: Dict[str, Any] | None = None,
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        new_variant_id = str(uuid4())

        parent = news_db.get_variant(parent_variant_id)
        if parent is None or not parent.get("card_id"):
            raise ValueError("parent variant not found")

        card_id = str(parent["card_id"])
        card = news_db.get_news(card_id=card_id, variant_id=None)
        if card is None:
            raise ValueError("card not found")
        # Depth increases by 1
        new_depth = int(parent.get("mutation_depth", 0)) + 1

        news_db.save_news(
            card_id=card_id,
            variant_id=new_variant_id,
            kind=card.kind,
            text=new_text,
            author_id=editor_id,
            parent_variant_id=parent_variant_id,
            mutation_depth=new_depth,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            published_at=now.isoformat(),
        )
        payload = NewsVariantMutatedPayload(
            card_id=card_id,
            new_variant_id=new_variant_id,
            parent_variant_id=parent_variant_id,
            editor_id=editor_id,
            new_text=new_text,
            influence_cost=float(influence_cost),
            risk_roll=risk_roll,
            mutated_at=now,
        )
        envelope = EventEnvelope[NewsVariantMutatedPayload](
            event_type=EventType.NEWS_VARIANT_MUTATED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=editor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return new_variant_id, event_json

    def deliver_variant(
        self,
        *,
        variant_id: str,
        to_player_id: str,
        from_actor_id: str,
        visibility_level: str,
        delivery_reason: str,
        correlation_id: UUID | None = None,
    ) -> tuple[str, EventEnvelopeJson]:
        now = self._now_game_utc()
        delivery_id = str(uuid4())

        variant = news_db.get_variant(variant_id)
        if variant is None or not variant.get("card_id"):
            raise ValueError("variant not found")

        card_id = str(variant["card_id"])

        news_db.deliver_variant(
            delivery_id=delivery_id,
            variant_id=variant_id,
            to_player_id=to_player_id,
            from_actor_id=from_actor_id,
            visibility_level=visibility_level,
            delivery_reason=delivery_reason,
        )
        payload = NewsDeliveredPayload(
            delivery_id=delivery_id,
            card_id=card_id,
            variant_id=variant_id,
            to_player_id=to_player_id,
            from_actor_id=from_actor_id,
            visibility_level=visibility_level,
            delivery_reason=delivery_reason,
            delivered_at=now,
        )
        envelope = EventEnvelope[NewsDeliveredPayload](
            event_type=EventType.NEWS_DELIVERED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=from_actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return delivery_id, event_json

    def propagate_to_followers(
        self,
        *,
        variant_id: str,
        from_actor_id: str,
        visibility_level: str,
        spend_influence: float = 0.0,
        limit: int = 50,
        correlation_id: UUID | None = None,
    ) -> List[EventEnvelopeJson]:
        # v0：只做一跳传播，从 from_actor_id 投递给其 followers
        followers = news_db.list_followers(followee_id=from_actor_id, limit=int(limit))

        delivered_events: List[EventEnvelopeJson] = []
        for to_player_id in followers:
            _delivery_id, event_json = self.deliver_variant(
                variant_id=variant_id,
                to_player_id=to_player_id,
                from_actor_id=from_actor_id,
                visibility_level=visibility_level,
                delivery_reason="SOCIAL_PROPAGATION",
                correlation_id=correlation_id,
            )
            delivered_events.append(event_json)

        return delivered_events

    def broadcast_variant(
        self,
        *,
        variant_id: str,
        channel: str,
        visibility_level: str,
        actor_id: str,
        limit_users: int = 5000,
        correlation_id: UUID | None = None,
    ) -> tuple[int, EventEnvelopeJson]:
        broadcast_id = str(uuid4())
        corr = correlation_id or uuid4()
        users = news_db.list_all_users(limit=int(limit_users))

        count = 0
        for to_player_id in users:
            _delivery_id, _delivery_event = self.deliver_variant(
                variant_id=variant_id,
                to_player_id=to_player_id,
                from_actor_id=actor_id,
                visibility_level=visibility_level,
                delivery_reason="BROADCAST",
                correlation_id=corr,
            )
            count += 1

        variant = news_db.get_variant(variant_id)
        card_id = str((variant or {}).get("card_id") or "")

        payload = NewsBroadcastedPayload(
            broadcast_id=broadcast_id,
            card_id=card_id,
            variant_id=variant_id,
            channel=channel,
            delivered_count=count,
            broadcasted_at=self._now_game_utc(),
        )
        envelope = EventEnvelope[NewsBroadcastedPayload](
            event_type=EventType.NEWS_BROADCASTED,
            correlation_id=corr,
            actor=EventActor(user_id=actor_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return count, event_json

    def list_inbox(self, *, player_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        return news_db.list_inbox(user_id=player_id, limit=int(limit))

    def get_variant_context(self, *, variant_id: str) -> Dict[str, Any] | None:
        v = news_db.get_variant(variant_id)
        if v is None:
            return None
        card_id = str(v.get("card_id") or "")
        if not card_id:
            return None

        card = news_db.get_news(card_id=card_id, variant_id=None)
        if card is None:
            return None

        truth_payload_json = json.dumps(card.truth_payload or {}, ensure_ascii=False)
        return {
            "text": v.get("text") or "",
            "author_id": v.get("author_id") or "",
            "mutation_depth": int(v.get("mutation_depth") or 0),
            "symbols": card.symbols or [],
            "truth_payload_json": truth_payload_json,
            "kind": card.kind,
        }

    def grant_ownership(
        self,
        *,
        card_id: str,
        to_user_id: str,
        granter_id: str,
        correlation_id: UUID | None = None,
    ) -> EventEnvelopeJson:
        now = self._now_game_utc()
        news_db.grant_ownership(card_id=card_id, user_id=to_user_id, granter_id=granter_id)

        payload = NewsOwnershipGrantedPayload(
            card_id=card_id,
            to_user_id=to_user_id,
            granter_id=granter_id,
            granted_at=now,
        )
        envelope = EventEnvelope[NewsOwnershipGrantedPayload](
            event_type=EventType.NEWS_OWNERSHIP_GRANTED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=granter_id),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return event_json

    def transfer_ownership(
        self,
        *,
        card_id: str,
        from_user_id: str,
        to_user_id: str,
        transferred_by: str,
        correlation_id: UUID | None = None,
    ) -> EventEnvelopeJson:
        if from_user_id == to_user_id:
            raise ValueError("from_user_id and to_user_id must be different")

        now = self._now_game_utc()
        news_db.transfer_ownership(
            card_id=card_id, from_user_id=from_user_id, to_user_id=to_user_id, transferred_by=transferred_by
        )

        payload = NewsOwnershipTransferredPayload(
            card_id=card_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            transferred_by=transferred_by,
            transferred_at=now,
        )
        envelope = EventEnvelope[NewsOwnershipTransferredPayload](
            event_type=EventType.NEWS_OWNERSHIP_TRANSFERRED,
            correlation_id=correlation_id or uuid4(),
            actor=EventActor(user_id=transferred_by),
            payload=payload,
        )
        event_json = EventEnvelopeJson.from_envelope(envelope)
        self._event_store.append(event_json)
        return event_json

    def list_owned_cards(self, *, user_id: str, limit: int = 200) -> List[str]:
        rows = news_db.list_owned_cards(user_id=user_id, limit=int(limit))
        return [str(r.get("card_id")) for r in rows if r.get("card_id")]

    def ensure_bot_users(self, bot_ids: List[str]) -> None:
        """确保内置机器人在新闻用户表中存在"""
        for bot_id in bot_ids:
            news_db.create_user(bot_id)

    def init_news_seed_data(self) -> None:
        """初始化预设的新闻卡牌组"""
        if news_db.count_cards() > 0:
            return

        seeds = [
            {
                "kind": "EARNINGS",
                "symbols": ["NEURALINK"],
                "text": "Neuralink 脑机接口三期临床实验数据远超预期。",
                "truth_payload": {
                    "impact": 0.15,
                    "direction": "UP",
                    "intensity": 0.62,
                    "ttl_seconds": 5400,
                    "reliability_prior": 0.85,
                    "deception_risk": 0.12,
                    "worldview": "cyberpunk_clinical_breakthrough",
                },
            },
            {
                "kind": "MILITARY",
                "symbols": ["BLUEGOLD"],
                "text": "BlueGold 获得北方联盟 500 亿信用点防御订单。",
                "truth_payload": {
                    "impact": 0.2,
                    "direction": "UP",
                    "intensity": 0.58,
                    "ttl_seconds": 4200,
                    "reliability_prior": 0.74,
                    "deception_risk": 0.2,
                    "worldview": "cyberpunk_defense_contract",
                },
            },
            {
                "kind": "ENERGY",
                "symbols": ["MARS_GEN"],
                "text": "火星二号核聚变电站发生容器泄漏事故。",
                "truth_payload": {
                    "impact": -0.25,
                    "direction": "DOWN",
                    "intensity": 0.64,
                    "ttl_seconds": 3600,
                    "reliability_prior": 0.77,
                    "deception_risk": 0.18,
                    "worldview": "cyberpunk_infrastructure_risk",
                },
            },
            {
                "kind": "FINANCE",
                "symbols": ["CIVILBANK"],
                "text": "联邦储备局宣布将维持当前基准利率不变。",
                "truth_payload": {
                    "impact": 0.02,
                    "direction": "STABLE",
                    "intensity": 0.35,
                    "ttl_seconds": 4800,
                    "reliability_prior": 0.82,
                    "deception_risk": 0.08,
                    "worldview": "cyberpunk_policy_signal",
                },
            }
        ]

        for s in seeds:
            card_id, _ = self.create_card(
                kind=s["kind"],
                image_anchor_id=None,
                image_uri=None,
                truth_payload=s["truth_payload"],
                symbols=s["symbols"],
                tags=["seed"],
                actor_id="system"
            )
            # 默认给系统生成一个变体
            self.emit_variant(
                card_id=card_id,
                author_id="system",
                text=s["text"]
            )

    def get_preset_template(self, kind: str, symbols: List[str]) -> str:
        """获取预设的情报模板并填充符号"""
        templates = self._preset_templates()
        kind_key = kind.upper()
        pool = templates.get(kind_key, templates["RUMOR"])
        text = random.choice(pool)
        
        symbol_str = ", ".join(symbols) if symbols else "某知名企业"
        return text.format(symbol=symbol_str)

    def get_preset_templates(self, kind: str, symbols: List[str]) -> List[str]:
        templates = self._preset_templates()
        kind_key = kind.upper()
        pool = templates.get(kind_key, templates["RUMOR"])
        symbol_str = ", ".join(symbols) if symbols else "某知名企业"
        return [str(t).format(symbol=symbol_str) for t in pool]

