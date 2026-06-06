from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class StoreTriggerMode(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    MANUAL = "MANUAL"
    AUTO_CHAIN = "AUTO_CHAIN"


class CardRarity(str, Enum):
    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    EPIC = "EPIC"
    LEGENDARY = "LEGENDARY"


@dataclass
class NewsPrototype:
    kind: str
    id: str
    templates: List[str]
    description: str
    namespace: str = "base"
    rarity: CardRarity = CardRarity.COMMON
    weight: float = 1.0
    faction: Optional[str] = None
    default_intensity: float = 0.5
    default_ttl_hours: int = 6
    image_pool: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    behavior_bindings: Dict[str, Any] = field(default_factory=dict)
    price_modifier: float = 1.0
    store_price_cash: float = 0.0
    store_requires_symbols: bool = False
    store_trigger_mode: StoreTriggerMode = StoreTriggerMode.IMMEDIATE
    store_chain_kind: Optional[str] = None
    store_chain_defaults: Dict[str, Any] = field(default_factory=dict)

    @property
    def full_id(self) -> str:
        return f"{self.namespace}:{self.id}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any], namespace: str = "base") -> NewsPrototype:
        payload = dict(data)
        if "rarity" in payload:
            payload["rarity"] = CardRarity(str(payload["rarity"]).upper())
        if "store_trigger_mode" in payload:
            payload["store_trigger_mode"] = StoreTriggerMode(str(payload["store_trigger_mode"]).upper())
        if "store_chain_kind" in payload and payload["store_chain_kind"] is not None:
            payload["store_chain_kind"] = str(payload["store_chain_kind"]).upper()
        payload.setdefault("namespace", namespace)
        return cls(**payload)

    def resolve_store_price_cash(self, fallback: float | None = None) -> float:
        value = self.store_price_cash if self.store_price_cash is not None else fallback
        return float(value or 0.0)

    def resolve_store_trigger_mode(self) -> StoreTriggerMode:
        mode = self.store_trigger_mode
        if isinstance(mode, StoreTriggerMode):
            return mode
        return StoreTriggerMode(str(mode).upper())

    def resolve_store_chain_defaults(self) -> Dict[str, Any]:
        return dict(self.store_chain_defaults or {})

    def resolve_store_chain_kind(self) -> str:
        return str(self.store_chain_kind or self.kind).upper()

    def resolve_store_catalog_item(self, *, price_cash: float, symbol: str | None = None) -> Dict[str, Any]:
        return {
            "kind": str(self.kind),
            "price_cash": float(price_cash),
            "requires_symbols": bool(self.store_requires_symbols),
            "trigger_mode": self.resolve_store_trigger_mode().value,
            "chain_kind": self.resolve_store_chain_kind(),
            "preview_text": "",
            "description": str(self.description),
            "rarity": str(getattr(self.rarity, "value", self.rarity)),
            "faction": self.faction,
            "default_ttl_hours": int(self.default_ttl_hours),
            "preview_image_uri": self.image_pool[0] if self.image_pool else None,
            "tags": list(self.tags),
            "symbol": symbol,
            "chain_defaults": self.resolve_store_chain_defaults() or None,
        }


class NewsPrototypeRegistry:
    def __init__(self):
        self._prototypes: Dict[str, NewsPrototype] = {}
        self._kind_map: Dict[str, List[NewsPrototype]] = {}
        self._load_defaults()
        self._load_from_mods()

    def _load_defaults(self) -> None:
        namespace = "base"
        defaults = [
            {
                "kind": "RUMOR",
                "id": "rumor_base",
                "templates": [
                    "暗网监控：{symbol} 的加密通讯协议已被暴力破解，大量核心机密正在霓虹街头贱卖。",
                    "霓虹街头流传：{symbol} 正在秘密测试一种能够通过神经链接直接改写市场感知的‘认知病毒’。",
                    "传闻 {symbol} 的地下基因实验室流出了非法的‘永生’变异样本，企业安保部队已封锁整个街区。",
                    "灰市消息：{symbol} 与月面交通局的补能协议接近签署，可能缓解其长期的能源成本压力。",
                ],
                "description": "来源不明的非官方消息，传播力强但可信度存疑。",
                "rarity": "COMMON",
                "weight": 10.0,
                "faction": "NEUTRAL",
                "default_ttl_hours": 6,
                "store_price_cash": 2000.0,
                "store_requires_symbols": False,
                "store_trigger_mode": "IMMEDIATE",
                "image_pool": ["/assets/news/rumor_1.webp", "/assets/news/rumor_2.webp"],
                "behavior_bindings": {
                    "market_volatility": 0.05,
                    "sentiment_shift": "UNSTABLE",
                },
            },
            {
                "kind": "LEAK",
                "id": "leak_base",
                "templates": [
                    "【绝密数据泄露】{symbol} 核心反应堆的损耗率已达临界点，一旦过载将引发足以抹平整个行政区的能量风暴。",
                    "内部邮件证实：{symbol} 的‘神谕’决策系统曾多次通过降维打击精准清除竞争对手，涉嫌违反《星际公平竞争法》。",
                    "泄露备忘录显示：{symbol} 的次世代冷核堆稳定性测试连续达标，董事会正在评估提前量产窗口。",
                ],
                "description": "内部流出的机密文件，极具杀伤力。",
                "rarity": "RARE",
                "weight": 5.0,
                "faction": "HACKER",
                "default_ttl_hours": 12,
                "store_price_cash": 15000.0,
                "store_requires_symbols": True,
                "store_trigger_mode": "IMMEDIATE",
                "image_pool": ["/assets/news/leak_1.webp"],
                "behavior_bindings": {
                    "price_impact": 0.15,
                    "insider_trading_signal": True,
                },
            },
            {
                "kind": "ANALYST_REPORT",
                "id": "report_base",
                "templates": [
                    "【深网分析】维持 {symbol} ‘强力买入’评级，其在‘意识上传’领域的专利垄断将确保其在下个纪元的霸权。",
                    "晨星深网覆盖：{symbol} 在非战争场景下的防御性现金流表现稳健，给出‘增持’建议。",
                ],
                "description": "机构发布的专业分析，对市场预期有显著引导。",
                "rarity": "UNCOMMON",
                "weight": 8.0,
                "faction": "CORPORATE",
                "default_ttl_hours": 24,
                "store_price_cash": 8000.0,
                "store_requires_symbols": True,
                "store_trigger_mode": "IMMEDIATE",
                "behavior_bindings": {
                    "institutional_bias": 0.08,
                    "target_price_modifier": 1.15,
                },
            },
            {
                "kind": "MAJOR_EVENT",
                "id": "major_base",
                "templates": [
                    "【重大突破】{symbol} 宣布其‘意识备份’技术成功实现了 99.99% 的灵魂完整度，正式开启‘数字永生’商业化元年。",
                    "【战略落地】{symbol} 联合多个主权节点完成跨区域清算协议升级，核心业务延迟和违约率同步下降。",
                ],
                "description": "足以改变行业格局的重大突发事件。",
                "rarity": "EPIC",
                "weight": 2.0,
                "faction": "CORPORATE",
                "default_ttl_hours": 48,
                "store_price_cash": 100000.0,
                "store_requires_symbols": True,
                "store_trigger_mode": "AUTO_CHAIN",
                "store_chain_defaults": {
                    "t0_seconds": 60,
                    "omen_interval_seconds": 10,
                    "abort_probability": 0.3,
                    "grant_count": 2,
                    "seed": 1,
                },
                "behavior_bindings": {
                    "sector_wide_impact": True,
                    "fundamental_shift": 0.25,
                },
            },
            {
                "kind": "WORLD_EVENT",
                "id": "world_base",
                "templates": [
                    "【联邦共识】星际联合议会通过《轨道重建法案》，关键能源与物流主干网将获得超额财政投放。",
                    "【和平窗口】多边停火协议进入执行期，跨境贸易与算力租赁恢复白名单通道。",
                ],
                "description": "影响所有参与者的宏观系统性事件。",
                "rarity": "LEGENDARY",
                "weight": 1.0,
                "faction": "GOVERNMENT",
                "default_ttl_hours": 72,
                "store_price_cash": 500000.0,
                "store_requires_symbols": False,
                "store_trigger_mode": "AUTO_CHAIN",
                "store_chain_defaults": {
                    "t0_seconds": 15,
                    "omen_interval_seconds": 10,
                    "abort_probability": 0.3,
                    "grant_count": 2,
                    "seed": 1,
                },
                "behavior_bindings": {
                    "macro_regime_change": True,
                    "global_liquidity_delta": 0.1,
                },
            },
        ]

        for data in defaults:
            self.register(NewsPrototype.from_dict(data, namespace=namespace))

    def _load_from_mods(self) -> None:
        mod_root = Path("mods/news")
        mod_root.mkdir(parents=True, exist_ok=True)
        for pack_dir in mod_root.iterdir():
            if not pack_dir.is_dir():
                continue
            for json_file in pack_dir.glob("blueprints/*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        self.register(NewsPrototype.from_dict(item, namespace=pack_dir.name))
                except Exception:
                    continue

    def register(self, prototype: NewsPrototype) -> None:
        self._prototypes[prototype.full_id] = prototype
        kind_key = prototype.kind.upper()
        self._kind_map.setdefault(kind_key, []).append(prototype)

    def get_blueprint(self, full_id: str) -> Optional[NewsPrototype]:
        return self._prototypes.get(full_id)

    def find_by_kind(self, kind: str) -> List[NewsPrototype]:
        return self._kind_map.get(str(kind or "").upper(), [])

    def list_blueprints(self) -> List[NewsPrototype]:
        return list(self._prototypes.values())


prototype_registry = NewsPrototypeRegistry()

# compatibility aliases
IntelligenceBlueprint = NewsPrototype
BlueprintRegistry = NewsPrototypeRegistry
registry = prototype_registry
