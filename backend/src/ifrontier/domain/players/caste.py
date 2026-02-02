from __future__ import annotations

"""玩家阶级/入局资产配置.

这里先内置几种简单阶级，后续可以根据设计文档扩展或改成从配置文件加载.

注意: 这些只是"创世分配"规则, 一旦账户创建完成, 后续所有资产变化都必须通过撮合+账本执行.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class CasteConfig:
    caste_id: str
    initial_cash: float
    initial_positions: Dict[str, float]


# 简单示例配置: 后续可以根据游戏阶级系统再细调数值
_CASTE_CONFIGS: Dict[str, CasteConfig] = {
    # 精英阶层: 高起步资金, 无初始持仓
    "ELITE": CasteConfig(
        caste_id="ELITE",
        initial_cash=1_000_000.0,
        initial_positions={},
    ),
    # 中产阶层: 中等资金
    "MIDDLE": CasteConfig(
        caste_id="MIDDLE",
        initial_cash=200_000.0,
        initial_positions={},
    ),
    # 工薪阶层: 较低资金
    "WORKING": CasteConfig(
        caste_id="WORKING",
        initial_cash=50_000.0,
        initial_positions={},
    ),
}


def get_caste_config(caste_id: str) -> CasteConfig | None:
    return _CASTE_CONFIGS.get(caste_id.upper())
