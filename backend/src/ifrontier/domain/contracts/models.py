from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Set


class ContractStatus(str, Enum):
    DRAFT = "DRAFT"
    SIGNED = "SIGNED"
    ACTIVE = "ACTIVE"
    SETTLED = "SETTLED"
    DEFAULTED = "DEFAULTED"

    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"


class ParticipationMode(str, Enum):
    # 默认：契约是“协定”，按 required_signers 全员签署规则推进
    ALL_SIGNERS = "ALL_SIGNERS"

    # 号召性质：受邀者可选择 join，不要求全员加入；签署仍由 required_signers 决定
    OPT_IN = "OPT_IN"


@dataclass(frozen=True)
class Contract:
    contract_id: str
    kind: str
    title: str
    terms: Dict[str, Any]
    parties: List[str]
    required_signers: List[str]
    signatures: Set[str]
    status: ContractStatus
    created_at: datetime
    updated_at: datetime