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


class NewsCardCreatedPayload(BaseModel):
    card_id: str
    kind: str
    image_anchor_id: str | None = None
    image_uri: str | None = None
    truth_payload: Dict[str, Any] | None = None
    symbols: List[str] = []
    tags: List[str] = []
    created_at: datetime


class NewsVariantEmittedPayload(BaseModel):
    card_id: str
    variant_id: str
    parent_variant_id: str | None = None
    author_id: str
    text: str
    influence_cost: float = 0.0
    risk_roll: Dict[str, Any] | None = None
    created_at: datetime


class NewsVariantMutatedPayload(BaseModel):
    card_id: str
    new_variant_id: str
    parent_variant_id: str
    editor_id: str
    new_text: str
    influence_cost: float = 0.0
    risk_roll: Dict[str, Any] | None = None
    mutated_at: datetime


class NewsDeliveredPayload(BaseModel):
    delivery_id: str
    card_id: str
    variant_id: str
    to_player_id: str
    from_actor_id: str
    visibility_level: str
    delivery_reason: str
    delivered_at: datetime


class NewsBroadcastedPayload(BaseModel):
    broadcast_id: str
    card_id: str
    variant_id: str
    channel: str
    delivered_count: int
    broadcasted_at: datetime


class NewsTruthRevealedPayload(BaseModel):
    card_id: str
    chain_id: str | None = None
    outcome: str  # RESOLVED / ABORTED
    image_anchor_id: str | None = None
    image_uri: str | None = None
    truth_payload: Dict[str, Any] | None = None
    revealed_at: datetime


class NewsChainStartedPayload(BaseModel):
    chain_id: str
    major_card_id: str
    kind: str
    t0_at: datetime | None = None
    started_at: datetime


class NewsChainAbortedPayload(BaseModel):
    chain_id: str
    major_card_id: str
    abort_reason: str | None = None
    aborted_at: datetime


class NewsPropagationSuppressedPayload(BaseModel):
    suppression_id: str
    actor_id: str
    target_chain_id: str | None = None
    target_card_id: str | None = None
    target_variant_id: str | None = None
    spend_influence: float
    scope: str
    suppressed_at: datetime


class NewsOwnershipGrantedPayload(BaseModel):
    card_id: str
    to_user_id: str
    granter_id: str
    granted_at: datetime


class NewsOwnershipTransferredPayload(BaseModel):
    card_id: str
    from_user_id: str
    to_user_id: str
    transferred_by: str
    transferred_at: datetime


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


class ContractDefaultedPayload(BaseModel):
    contract_id: str
    settlement_event_id: str
    fill_ratio: float
    shortfall_by_from: Dict[str, Any]
    defaulted_at: datetime


class ContractRuleExecutedPayload(BaseModel):
    contract_id: str
    rule_id: str
    evaluated: bool
    executed: bool
    reason: str | None = None
    settlement_event_id: str | None = None
    executed_at: datetime