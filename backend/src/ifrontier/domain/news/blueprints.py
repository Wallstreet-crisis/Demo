from __future__ import annotations
import json
import os
import glob
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from pathlib import Path

class CardRarity(str, Enum):
    COMMON = "COMMON"
    UNCOMMON = "UNCOMMON"
    RARE = "RARE"
    EPIC = "EPIC"
    LEGENDARY = "LEGENDARY"

@dataclass
class IntelligenceBlueprint:
    kind: str
    id: str
    templates: List[str]
    description: str
    rarity: CardRarity = CardRarity.COMMON
    weight: float = 1.0  # 出现权重
    faction: Optional[str] = None # 所属势力
    default_intensity: float = 0.5
    default_ttl_hours: int = 6
    image_pool: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    behavior_bindings: Dict[str, Any] = field(default_factory=dict)
    price_modifier: float = 1.0 # 价格修正系数

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IntelligenceBlueprint:
        if "rarity" in data:
            data["rarity"] = CardRarity(data["rarity"])
        return cls(**data)

class BlueprintRegistry:
    def __init__(self):
        self._blueprints: Dict[str, IntelligenceBlueprint] = {}
        self._kind_map: Dict[str, List[IntelligenceBlueprint]] = {}
        self._load_defaults()
        self._load_from_mods()

    def _load_defaults(self):
        # 基础默认模板
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
                "default_ttl_hours": 6,
                "image_pool": ["/assets/news/rumor_1.webp", "/assets/news/rumor_2.webp"]
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
                "default_ttl_hours": 12,
                "image_pool": ["/assets/news/leak_1.webp"]
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
                "default_ttl_hours": 24,
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
                "default_ttl_hours": 48,
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
                "default_ttl_hours": 72,
            }
        ]
        for data in defaults:
            bp = IntelligenceBlueprint.from_dict(data)
            self.register(bp)

    def _load_from_mods(self):
        # 尝试从 mods/news 目录加载 JSON 蓝图
        mod_dir = Path("mods/news")
        if not mod_dir.exists():
            # 如果不存在，尝试创建（可选，为了演示结构）
            try:
                mod_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                return

        for json_file in mod_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            self.register(IntelligenceBlueprint.from_dict(item))
                    elif isinstance(data, dict):
                        self.register(IntelligenceBlueprint.from_dict(data))
            except Exception as e:
                print(f"Failed to load news blueprint from {json_file}: {e}")

    def register(self, bp: IntelligenceBlueprint):
        self._blueprints[bp.id] = bp
        if bp.kind not in self._kind_map:
            self._kind_map[bp.kind] = []
        self._kind_map[bp.kind].append(bp)

    def get_blueprint(self, blueprint_id: str) -> Optional[IntelligenceBlueprint]:
        return self._blueprints.get(blueprint_id)

    def find_by_kind(self, kind: str) -> List[IntelligenceBlueprint]:
        return self._kind_map.get(kind.upper(), [])

    def list_blueprints(self) -> List[IntelligenceBlueprint]:
        return list(self._blueprints.values())

# Global registry instance
registry = BlueprintRegistry()
