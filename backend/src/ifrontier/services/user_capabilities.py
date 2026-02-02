from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ifrontier.services.chat import ChatService
from ifrontier.services.contract_agent import ContractAgent, ContractDraftResult
from ifrontier.services.contracts import ContractService
from ifrontier.services.matching import submit_limit_order, submit_market_order


@dataclass(frozen=True)
class UserCapabilityFacade:
    """用户能力门面：HostingAgent 只能通过本门面访问系统能力。

    约束：
    - 读：只能走用户可见的读接口（此处先复用现有 service 的公开方法）。
    - 写：只能走用户可操作的写接口。

    MVP 版本先提供最小子集，后续可继续扩展，不改 HostingAgent 的调用面。
    """

    user_id: str
    contract_service: ContractService
    contract_agent: ContractAgent
    chat_service: ChatService

    # --- Chat ---

    def send_public_message(
        self,
        *,
        message_type: str,
        content: str = "",
        payload: Optional[Dict[str, Any]] = None,
        anonymous: bool = False,
        alias: str | None = None,
    ):
        return self.chat_service.send_public_message(
            sender_id=self.user_id,
            message_type=message_type,
            content=content,
            payload=payload,
            anonymous=bool(anonymous),
            alias=alias,
        )

    def send_pm_message(
        self,
        *,
        thread_id: str,
        message_type: str,
        content: str = "",
        payload: Optional[Dict[str, Any]] = None,
        anonymous: bool = False,
        alias: str | None = None,
    ):
        return self.chat_service.send_pm_message(
            thread_id=thread_id,
            sender_id=self.user_id,
            message_type=message_type,
            content=content,
            payload=payload,
            anonymous=bool(anonymous),
            alias=alias,
        )

    def list_threads(self, *, limit: int = 200):
        return self.chat_service.list_threads(user_id=self.user_id, limit=limit)

    def list_public_messages(self, *, limit: int = 50, before: str | None = None):
        return self.chat_service.list_public_messages(limit=limit, before=before)

    def list_pm_messages(self, *, thread_id: str, limit: int = 50, before: str | None = None):
        return self.chat_service.list_pm_messages(thread_id=thread_id, limit=limit, before=before)

    # --- Contract agent (draft) ---

    def draft_contract(self, *, natural_language: str) -> ContractDraftResult:
        return self.contract_agent.draft(actor_id=self.user_id, natural_language=natural_language)

    # --- Contracts ---

    def create_contract(
        self,
        *,
        kind: str,
        title: str,
        terms: Dict[str, Any],
        parties: List[str],
        required_signers: List[str],
        participation_mode: str | None = None,
        invited_parties: List[str] | None = None,
    ) -> str:
        return self.contract_service.create_contract(
            kind=kind,
            title=title,
            terms=terms,
            parties=parties,
            required_signers=required_signers,
            participation_mode=participation_mode,
            invited_parties=invited_parties,
            actor_id=self.user_id,
        )

    def sign_contract(self, *, contract_id: str) -> str:
        status = self.contract_service.sign_contract(contract_id=contract_id, signer=self.user_id)
        return status.value

    def activate_contract(self, *, contract_id: str) -> None:
        self.contract_service.activate_contract(contract_id=contract_id, actor_id=self.user_id)

    def join_contract(self, *, contract_id: str) -> None:
        self.contract_service.join_contract(contract_id=contract_id, joiner=self.user_id)

    def create_proposal(self, *, contract_id: str, proposal_type: str, details: Dict[str, Any]) -> str:
        return self.contract_service.create_proposal(
            contract_id=contract_id,
            proposal_type=proposal_type,
            proposer=self.user_id,
            details=details,
        )

    def approve_proposal(self, *, contract_id: str, proposal_id: str) -> Dict[str, Any]:
        return self.contract_service.approve_proposal(
            contract_id=contract_id,
            proposal_id=proposal_id,
            approver=self.user_id,
        )

    # --- Trading ---

    def submit_limit_order(self, *, symbol: str, side: str, price: float, quantity: float):
        return submit_limit_order(
            account_id=self.user_id,
            symbol=symbol,
            side=side,
            price=float(price),
            quantity=float(quantity),
        )

    def submit_market_order(self, *, symbol: str, side: str, quantity: float):
        return submit_market_order(
            account_id=self.user_id,
            symbol=symbol,
            side=side,
            quantity=float(quantity),
        )
