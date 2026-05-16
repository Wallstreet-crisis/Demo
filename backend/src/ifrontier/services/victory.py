from __future__ import annotations

import enum
from typing import List, Optional, Dict, Any
from ifrontier.infra.sqlite.ledger import get_snapshot, AccountSnapshot
from ifrontier.infra.sqlite.market import get_last_price
from ifrontier.infra.sqlite.securities import list_securities
from ifrontier.infra.sqlite.db import get_connection
from ifrontier.core.logger import get_logger

_log = get_logger(__name__)

# 破产阈值
BANKRUPTCY_THRESHOLD = 2720.0

class PlayerStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    BANKRUPT = "BANKRUPT"
    WINNER = "WINNER"
    SPECTATOR = "SPECTATOR"
    RETIRED = "RETIRED"  # 中产阶级的退休状态

class VictoryConditionType(str, enum.Enum):
    TIME_LIMIT = "TIME_LIMIT"
    ULTIMATE_OWNER = "ULTIMATE_OWNER"
    MASS_BANKRUPTCY = "MASS_BANKRUPTCY"
    MM_DOMINATION = "MM_DOMINATION"
    SELF_MADE = "SELF_MADE"          # 平民胜利
    FINANCIAL_FREEDOM = "FINANCIAL_FREEDOM" # 中产胜利
    PHILOSOPHER = "PHILOSOPHER"      # 精英黑色幽默胜利

class VictoryService:
    def __init__(self):
        from ifrontier.services.market_maker import BASELINE_CAPITAL
        self.mm_baseline = BASELINE_CAPITAL

    def compute_total_valuation(self, account_id: str) -> float:
        """计算玩家总财富（现金 + 持仓市值）。"""
        try:
            snap = get_snapshot(account_id)
            total = float(snap.cash)
            for symbol, qty in snap.positions.items():
                if qty > 0:
                    price = get_last_price(symbol)
                    if price:
                        total += qty * price
            return total
        except Exception as e:
            _log.error(f"Failed to compute valuation for {account_id}: {e}")
            return 0.0

    def update_player_settlement(self, account_id: str) -> Dict[str, Any]:
        """单人结算：更新估值，检查多元终局。"""
        total = self.compute_total_valuation(account_id)
        snap = get_snapshot(account_id)
        
        if snap.status in {PlayerStatus.BANKRUPT, PlayerStatus.SPECTATOR, PlayerStatus.WINNER, PlayerStatus.RETIRED}:
            return {"status": snap.status, "achievement": None}

        new_status = PlayerStatus.ACTIVE
        achievement = None
        message = ""
        
        # 1. 破产判定
        if total < BANKRUPTCY_THRESHOLD:
            new_status = PlayerStatus.BANKRUPT
            message = "您的资金已跌破生存线。根据《市场避难所协议》，您已被剥夺操作权，转为观战模式。"
        
        # 2. 阶级专属终局逻辑
        # - WORKING (平民): 白手起家
        elif snap.caste_id == "WORKING" and total >= 1_000_000.0:
            new_status = PlayerStatus.WINNER
            achievement = VictoryConditionType.SELF_MADE
            message = "从一贫如洗到百万身家，你证明了资本神话的存在。你已出人头地！"

        # - MIDDLE (中产): 财务自由 (10倍初始资金且轻仓)
        elif snap.caste_id == "MIDDLE":
            # 计算总仓位占比
            stock_value = total - float(snap.cash)
            stock_ratio = stock_value / total if total > 0 else 0
            if total >= 2_000_000.0 and stock_ratio < 0.05:
                new_status = PlayerStatus.RETIRED
                achievement = VictoryConditionType.FINANCIAL_FREEDOM
                message = "你已达成财务自由并成功空仓避险。你决定在塞浦路斯买个海滩退休，不再参与这该死的市场。"

        # - ELITE (精英): 黑色幽默 [归于平凡] (赔光但活着)
        elif snap.caste_id == "ELITE" and BANKRUPTCY_THRESHOLD < total < 5000.0:
            # 这里可以设定为一个特殊胜利条件：体验过巅峰后的坦然
            new_status = PlayerStatus.WINNER
            achievement = VictoryConditionType.PHILOSOPHER
            message = "从亿万富豪到一文不名，你在破产边缘感受到了久违的宁静。你赢得了'哲学大师'成就。"

        # 3. 绝对支配 (支配做市商)
        if total >= self.mm_baseline * 1.1:
            new_status = PlayerStatus.WINNER
            achievement = VictoryConditionType.MM_DOMINATION
            message = f"你的财富已经超越了做市商的承载极限。你不是在交易，你就是市场本身。"

        if new_status != snap.status:
            conn = get_connection()
            with conn:
                conn.execute(
                    "UPDATE accounts SET total_valuation = ?, status = ? WHERE account_id = ?",
                    (total, new_status.value, account_id),
                )
        
        return {
            "status": new_status.value,
            "achievement": achievement,
            "message": message,
            "valuation": total
        }

    def check_global_victory(self, settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """检查全局胜利/结束条件。"""
        # 获取所有玩家快照
        conn = get_connection()
        players = conn.execute(
            "SELECT account_id, owner_type, status, total_valuation FROM accounts WHERE owner_type = 'user'"
        ).fetchall()
        
        if not players:
            return None

        # 终产者模式
        threshold = settings.get("ultimate_owner_threshold", self.mm_baseline * 1.5)
        for p in players:
            if p["total_valuation"] >= threshold:
                return {
                    "type": VictoryConditionType.ULTIMATE_OWNER,
                    "winner": p["account_id"],
                    "reason": f"财富集中度达到临界值。玩家 {p['account_id']} 已成为终产者，地球上每一口呼吸的空气现在都属于他/她。仿真结束。",
                    "achievement": "THE_ONE"
                }

        # 批量破产模式
        active_players = [p for p in players if p["status"] == PlayerStatus.ACTIVE]
        if settings.get("mass_bankruptcy_mode") and len(active_players) <= settings.get("min_active_players", 1):
            winner = active_players[0]["account_id"] if active_players else "NONE"
            return {
                "type": VictoryConditionType.MASS_BANKRUPTCY,
                "winner": winner,
                "reason": "市场已彻底枯竭，除了最后一位幸存者，所有人都已在财务上灰飞烟灭。资本的荒原上只剩下一串数字。",
                "achievement": "LAST_SURVIVOR"
            }

        return None
