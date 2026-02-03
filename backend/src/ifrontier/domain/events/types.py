from enum import Enum


class EventType(str, Enum):
    NEWS_CREATED = "news.created"
    NEWS_TEXT_MUTATED = "news.text_mutated"
    NEWS_PROPAGATED = "news.propagated"

    NEWS_CARD_CREATED = "news.card_created"
    NEWS_VARIANT_EMITTED = "news.variant_emitted"
    NEWS_VARIANT_MUTATED = "news.variant_mutated"
    NEWS_DELIVERED = "news.delivered"
    NEWS_BROADCASTED = "news.broadcasted"
    NEWS_TRUTH_REVEALED = "news.truth_revealed"
    NEWS_CHAIN_STARTED = "news.chain_started"
    NEWS_CHAIN_ABORTED = "news.chain_aborted"
    NEWS_PROPAGATION_SUPPRESSED = "news.propagation_suppressed"

    NEWS_OWNERSHIP_GRANTED = "news.ownership_granted"
    NEWS_OWNERSHIP_TRANSFERRED = "news.ownership_transferred"

    AI_COMMONBOT_DECISION = "ai.commonbot.decision"
    AI_CONTRACT_DRAFTED = "ai.contract.drafted"
    AI_WHISPERER_ASSESSMENT = "ai.whisperer.assessment"
    AI_WORLD_EVENT_OMEN_EMITTED = "ai.world_event.omen_emitted"
    AI_WORLD_EVENT_PURCHASED = "ai.world_event.purchased"
    AI_WORLD_EVENT_RESOLVED = "ai.world_event.resolved"
    AI_PLAYER_AGENT_TASK_SUBMITTED = "ai.player_agent.task_submitted"
    AI_PLAYER_AGENT_TASK_COMPLETED = "ai.player_agent.task_completed"

    AI_HOSTING_STATE_CHANGED = "ai.hosting.state_changed"
    AI_HOSTING_ACTION_TAKEN = "ai.hosting.action_taken"

    CHAT_THREAD_OPENED = "chat.thread.opened"
    CHAT_MESSAGE_SENT = "chat.message.sent"
    CHAT_INTRO_FEE_QUOTED = "chat.intro_fee.quoted"
    CHAT_INTRO_FEE_PAID = "chat.intro_fee.paid"

    WEALTH_PUBLIC_REFRESHED = "wealth.public.refreshed"

    TRADE_INTENT_SUBMITTED = "trade.intent_submitted"
    TRADE_EXECUTED = "trade.executed"

    CONTRACT_CREATED = "contract.created"
    CONTRACT_SIGNED = "contract.signed"
    CONTRACT_ACTIVATED = "contract.activated"

    CONTRACT_JOINED = "contract.joined"
    CONTRACT_PROPOSAL_CREATED = "contract.proposal_created"
    CONTRACT_PROPOSAL_APPROVED = "contract.proposal_approved"
    CONTRACT_SUSPENDED = "contract.suspended"
    CONTRACT_AMENDED = "contract.amended"
    CONTRACT_TERMINATED = "contract.terminated"

    CONTRACT_SETTLED = "contract.settled"

    CONTRACT_DEFAULTED = "contract.defaulted"

    CONTRACT_RULE_EXECUTED = "contract.rule_executed"

    DISCLOSURE_EMITTED = "disclosure.emitted"

    SETTLEMENT_TICK_OPENED = "settlement.tick_opened"
    SETTLEMENT_TICK_CLOSED = "settlement.tick_closed"
