from enum import Enum


class EventType(str, Enum):
    NEWS_CREATED = "news.created"
    NEWS_TEXT_MUTATED = "news.text_mutated"
    NEWS_PROPAGATED = "news.propagated"

    AI_COMMONBOT_DECISION = "ai.commonbot.decision"
    AI_CONTRACT_DRAFTED = "ai.contract.drafted"
    AI_WHISPERER_ASSESSMENT = "ai.whisperer.assessment"
    AI_WORLD_EVENT_OMEN_EMITTED = "ai.world_event.omen_emitted"
    AI_WORLD_EVENT_PURCHASED = "ai.world_event.purchased"
    AI_WORLD_EVENT_RESOLVED = "ai.world_event.resolved"
    AI_PLAYER_AGENT_TASK_SUBMITTED = "ai.player_agent.task_submitted"
    AI_PLAYER_AGENT_TASK_COMPLETED = "ai.player_agent.task_completed"

    TRADE_INTENT_SUBMITTED = "trade.intent_submitted"
    TRADE_EXECUTED = "trade.executed"

    CONTRACT_CREATED = "contract.created"
    CONTRACT_SIGNED = "contract.signed"
    CONTRACT_ACTIVATED = "contract.activated"

    DISCLOSURE_EMITTED = "disclosure.emitted"

    SETTLEMENT_TICK_OPENED = "settlement.tick_opened"
    SETTLEMENT_TICK_CLOSED = "settlement.tick_closed"
