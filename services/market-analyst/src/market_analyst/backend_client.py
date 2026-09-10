from typing import Protocol

import httpx
from distributed_agent_contracts import (
    AppendConversationMessageRequest,
    ConversationMessage,
    ConversationReviewContext,
    MarketReportDraft,
    PersistMarketReportDraftRequest,
    PublishApprovedMarketReportRequest,
    PublishMarketReportRequest,
    PublishMarketReportResponse,
    ReportReviewDecision,
    ReportReviewEvent,
)

from market_analyst.settings import MarketResearchSettings


class MarketPublisher(Protocol):
    async def publish(self, request: PublishMarketReportRequest) -> PublishMarketReportResponse: ...

    async def persist_draft(
        self, request: PersistMarketReportDraftRequest
    ) -> MarketReportDraft: ...

    async def record_review(
        self, conversation_id: str, decision: ReportReviewDecision
    ) -> ReportReviewEvent: ...

    async def append_message(
        self, request: AppendConversationMessageRequest
    ) -> ConversationMessage: ...

    async def get_review_context(self, conversation_id: str) -> ConversationReviewContext: ...

    async def publish_approved(
        self, request: PublishApprovedMarketReportRequest
    ) -> PublishMarketReportResponse: ...


class BackendMarketPublisher:
    def __init__(self, settings: MarketResearchSettings) -> None:
        self._base_url = settings.backend_base_url
        self._timeout = settings.backend_timeout_seconds
        self._token = settings.backend_api_token

    async def publish(self, request: PublishMarketReportRequest) -> PublishMarketReportResponse:
        return await self._post(
            "/internal/markets/reports",
            request,
            PublishMarketReportResponse,
            request.idempotency_key,
        )

    async def persist_draft(self, request: PersistMarketReportDraftRequest) -> MarketReportDraft:
        return await self._post(
            "/internal/report-drafts",
            request,
            MarketReportDraft,
            request.idempotency_key,
        )

    async def record_review(
        self, conversation_id: str, decision: ReportReviewDecision
    ) -> ReportReviewEvent:
        return await self._post(
            f"/internal/conversations/{conversation_id}/review-actions",
            decision,
            ReportReviewEvent,
            decision.idempotency_key,
        )

    async def append_message(
        self, request: AppendConversationMessageRequest
    ) -> ConversationMessage:
        return await self._post(
            "/internal/conversation-messages",
            request,
            ConversationMessage,
            request.idempotency_key,
        )

    async def get_review_context(self, conversation_id: str) -> ConversationReviewContext:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.get(
                f"/internal/conversations/{conversation_id}/review-context",
                headers=self._headers(),
            )
            response.raise_for_status()
        return ConversationReviewContext.model_validate(response.json())

    async def publish_approved(
        self, request: PublishApprovedMarketReportRequest
    ) -> PublishMarketReportResponse:
        return await self._post(
            "/internal/report-drafts/publish",
            request,
            PublishMarketReportResponse,
            request.idempotency_key,
        )

    async def _post(self, path, request, response_model, idempotency_key):
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post(
                path,
                headers=self._headers(idempotency_key),
                json=request.model_dump(mode="json"),
            )
            response.raise_for_status()
        return response_model.model_validate(response.json())

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers
