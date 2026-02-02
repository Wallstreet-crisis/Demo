from __future__ import annotations
from typing import Any, Dict, List
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NewsCreatedPayload(BaseModel):
    news_id: str
    variant_id: str
    kind: str
    visual_truth: str
    original_image_uri: str
    initial_text: str
    created_at: datetime


class NewsTextMutatedPayload(BaseModel):
    news_id: str
    new_variant_id: str
    parent_variant_id: str
    editor_user_id: str
    mutated_text: str
    influence_cost: int
    mutated_at: datetime


class NewsPropagatedPayload(BaseModel):
    news_id: str
    variant_id: str
    from_user_id: str
    to_user_id: str
    weight: float
    influence_cost: int
    propagated_at: datetime


class TradeIntentSubmittedPayload(BaseModel):
    intent_id: str
    user_id: str
    symbol: str
    side: str  # BUY / SELL
    size: float
    price_hint: float | None = None
    created_at: datetime


class DisclosureEmittedPayload(BaseModel):
    disclosure_id: str
    trigger: str
    related_trade_id: Optional[str] = None
    related_contract_id: Optional[str] = None
    emitted_at: datetime


class SettlementTickOpenedPayload(BaseModel):
    tick_id: str
    opened_at: datetime


class SettlementTickClosedPayload(BaseModel):
    tick_id: str
    closed_at: datetime
    matched_trades: int


class AiCommonBotDecisionPayload(BaseModel):
    bot_id: str
    tick_id: str
    asset_symbol: str
    action: str
    confidence: float
    w_visual: float
    w_text: float
    w_trend: float
    decided_at: datetime


class AiContractDraftedPayload(BaseModel):
    draft_id: str
    requester_user_id: str
    natural_language: str
    python_preview: str
    risk_rating: str
    drafted_at: datetime


class AiWhispererAssessmentPayload(BaseModel):
    assessment_id: str
    requester_user_id: str
    news_id: str
    variant_id: str
    conflict_score: float
    summary: str
    assessed_at: datetime


class AiWorldOmenEmittedPayload(BaseModel):
    omen_id: str
    event_id: str
    omen_news_id: str
    t_minus_seconds: int
    emitted_at: datetime


class AiWorldEventPurchasedPayload(BaseModel):
    world_event_id: str
    purchaser_user_id: str
    kind: str
    will_factor: float
    purchased_at: datetime


class AiWorldEventResolvedPayload(BaseModel):
    world_event_id: str
    outcome: str
    resolved_at: datetime


class AiPlayerAgentTaskSubmittedPayload(BaseModel):
    task_id: str
    requester_user_id: str
    instruction: str
    submitted_at: datetime


class AiPlayerAgentTaskCompletedPayload(BaseModel):
    task_id: str
    requester_user_id: str
    result_summary: str
    completed_at: datetime


class ContractCreatedPayload(BaseModel):
    contract_id: str
    kind: str
    title: str
    terms: Dict[str, Any]
    parties: List[str]
    required_signers: List[str]
    created_at: datetime
 
 
class ContractSignedPayload(BaseModel):
    contract_id: str
    signer: str
    signed_at: datetime
 
 
class ContractActivatedPayload(BaseModel):
    contract_id: str
    activated_at: datetime


class ContractJoinedPayload(BaseModel):
    contract_id: str
    joiner: str
    joined_at: datetime


class ContractProposalCreatedPayload(BaseModel):
    contract_id: str
    proposal_id: str
    proposal_type: str
    proposer: str
    details: Dict[str, Any]
    created_at: datetime


class ContractProposalApprovedPayload(BaseModel):
    contract_id: str
    proposal_id: str
    approver: str
    approved_at: datetime


class ContractSettledPayload(BaseModel):
    contract_id: str
    settlement_event_id: str
    settled_at: datetime


class ContractRuleExecutedPayload(BaseModel):
    contract_id: str
    rule_id: str
    evaluated: bool
    executed: bool
    reason: str | None = None
    settlement_event_id: str | None = None
    executed_at: datetime