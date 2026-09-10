import asyncio
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from distributed_agent_contracts import (
    AppendConversationMessageRequest,
    ConversationMessage,
    ConversationReviewContext,
    MarketReportDraft,
    PersistMarketReportDraftRequest,
    PublishApprovedMarketReportRequest,
    PublishMarketReportRequest,
    PublishMarketReportResponse,
    ReportReviewActionInput,
    ReportReviewDecision,
    ReportReviewEvent,
)
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool

from backend.config import BackendSettings
from backend.models import MarketAnalysisResponse, MarketSummary
from backend.repository import (
    DashboardRepository,
    DraftConflictError,
    DraftNotFoundError,
    MarketNotFoundError,
    PublicationConflictError,
)
from backend.review_runtime import LangGraphReviewResumer, ReviewDispatcher, ReviewResumer


class MarketReader(Protocol):
    async def list_markets(self) -> list[MarketSummary]: ...

    async def get_market(self, market_id: str) -> MarketAnalysisResponse: ...

    async def publish_market_report(
        self, request: PublishMarketReportRequest
    ) -> PublishMarketReportResponse: ...

    async def persist_market_report_draft(
        self, request: PersistMarketReportDraftRequest
    ) -> MarketReportDraft: ...

    async def get_pending_draft(self, conversation_id: UUID) -> MarketReportDraft: ...

    async def record_report_review(
        self,
        conversation_id: UUID,
        decision: ReportReviewDecision,
        *,
        delivery_confirmed: bool = False,
    ) -> ReportReviewEvent: ...

    async def append_conversation_message(
        self, request: AppendConversationMessageRequest
    ) -> ConversationMessage: ...

    async def get_review_context(
        self, conversation_id: UUID, *, message_limit: int = 12
    ) -> ConversationReviewContext: ...

    async def publish_approved_draft(
        self, request: PublishApprovedMarketReportRequest
    ) -> PublishMarketReportResponse: ...


def create_app(
    settings: BackendSettings | None = None,
    repository: MarketReader | None = None,
    review_resumer: ReviewResumer | None = None,
) -> FastAPI:
    runtime_settings = settings or BackendSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if repository is not None:
            app.state.repository = repository
            app.state.review_resumer = review_resumer
            app.state.review_dispatcher = None
            app.state.ready = True
            yield
            return

        pool = AsyncConnectionPool(
            runtime_settings.database_url,
            min_size=runtime_settings.pool_min_size,
            max_size=runtime_settings.pool_max_size,
            open=False,
        )
        await pool.open(wait=True, timeout=10)
        app.state.repository = DashboardRepository(pool)
        app.state.review_resumer = review_resumer or LangGraphReviewResumer(runtime_settings)
        app.state.review_dispatcher = ReviewDispatcher(
            app.state.repository,
            app.state.review_resumer,
            action_timeout_seconds=runtime_settings.review_action_timeout_seconds,
        )
        dispatcher_task = asyncio.create_task(
            app.state.review_dispatcher.run(), name="review-action-dispatcher"
        )
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            app.state.review_dispatcher.stop()
            await dispatcher_task
            await pool.close()

    app = FastAPI(title="Indie Lab Backend", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type", "Idempotency-Key", "X-Actor-Id"],
    )
    app.state.ready = False

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"service": "backend", "status": "ok"}

    @app.get("/ready")
    async def ready():
        if not app.state.ready:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"service": "backend", "status": "ready"}

    @app.get("/api/markets", response_model=list[MarketSummary])
    async def list_markets() -> list[MarketSummary]:
        return await app.state.repository.list_markets()

    @app.get("/api/markets/{market_id}", response_model=MarketAnalysisResponse)
    async def get_market(market_id: str) -> MarketAnalysisResponse:
        try:
            return await app.state.repository.get_market(market_id)
        except MarketNotFoundError as error:
            raise HTTPException(status_code=404, detail="Market not found") from error

    @app.post(
        "/internal/markets/reports",
        response_model=PublishMarketReportResponse,
        status_code=201,
    )
    async def publish_market_report(
        request: PublishMarketReportRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> PublishMarketReportResponse:
        expected = runtime_settings.internal_api_token
        supplied = authorization.removeprefix("Bearer ") if authorization else ""
        if expected and not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="Invalid service credential")
        if idempotency_key != request.idempotency_key:
            raise HTTPException(status_code=400, detail="Idempotency key mismatch")
        try:
            return await app.state.repository.publish_market_report(request)
        except PublicationConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/internal/report-drafts",
        response_model=MarketReportDraft,
        status_code=201,
    )
    async def persist_market_report_draft(
        request: PersistMarketReportDraftRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> MarketReportDraft:
        _authorize_internal(runtime_settings, authorization)
        _validate_idempotency_key(idempotency_key, request.idempotency_key)
        try:
            return await app.state.repository.persist_market_report_draft(request)
        except DraftConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/internal/conversation-messages",
        response_model=ConversationMessage,
        status_code=201,
    )
    async def append_conversation_message(
        request: AppendConversationMessageRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ConversationMessage:
        _authorize_internal(runtime_settings, authorization)
        _validate_idempotency_key(idempotency_key, request.idempotency_key)
        return await app.state.repository.append_conversation_message(request)

    @app.get(
        "/internal/conversations/{conversation_id}/review-context",
        response_model=ConversationReviewContext,
    )
    async def get_review_context(
        conversation_id: UUID,
        authorization: str | None = Header(default=None),
    ) -> ConversationReviewContext:
        _authorize_internal(runtime_settings, authorization)
        return await app.state.repository.get_review_context(conversation_id)

    @app.post(
        "/internal/report-drafts/publish",
        response_model=PublishMarketReportResponse,
        status_code=201,
    )
    async def publish_approved_draft(
        request: PublishApprovedMarketReportRequest,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> PublishMarketReportResponse:
        _authorize_internal(runtime_settings, authorization)
        _validate_idempotency_key(idempotency_key, request.idempotency_key)
        try:
            return await app.state.repository.publish_approved_draft(request)
        except (DraftConflictError, PublicationConflictError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/internal/conversations/{conversation_id}/review-actions",
        response_model=ReportReviewEvent,
        status_code=201,
    )
    async def record_internal_review(
        conversation_id: UUID,
        decision: ReportReviewDecision,
        authorization: str | None = Header(default=None),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ReportReviewEvent:
        _authorize_internal(runtime_settings, authorization)
        _validate_idempotency_key(idempotency_key, decision.idempotency_key)
        try:
            return await app.state.repository.record_report_review(
                conversation_id, decision, delivery_confirmed=True
            )
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail="Draft not found") from error
        except DraftConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get(
        "/api/conversations/{conversation_id}/pending-review",
        response_model=MarketReportDraft,
    )
    async def get_pending_review(conversation_id: UUID) -> MarketReportDraft:
        try:
            return await app.state.repository.get_pending_draft(conversation_id)
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail="Pending review not found") from error

    @app.post(
        "/api/conversations/{conversation_id}/review-actions",
        response_model=ReportReviewEvent,
        status_code=202,
    )
    async def review_report(
        conversation_id: UUID,
        action: ReportReviewActionInput,
        actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ReportReviewEvent:
        if not actor_id:
            raise HTTPException(status_code=401, detail="Authenticated actor is required")
        _validate_idempotency_key(idempotency_key, action.idempotency_key)
        decision = ReportReviewDecision(
            **action.model_dump(mode="python"),
            actor_id=actor_id,
            action_deadline_at=datetime.now(UTC)
            + timedelta(seconds=runtime_settings.review_action_timeout_seconds),
        )
        try:
            event = await app.state.repository.record_report_review(conversation_id, decision)
            if app.state.review_dispatcher is not None:
                await app.state.review_dispatcher.dispatch(event.event_id)
            elif app.state.review_resumer is not None:
                await app.state.review_resumer.resume(conversation_id, decision, event.event_id)
            return event
        except DraftNotFoundError as error:
            raise HTTPException(status_code=404, detail="Draft not found") from error
        except DraftConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return app


def _authorize_internal(settings: BackendSettings, authorization: str | None) -> None:
    expected = settings.internal_api_token
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if expected and not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid service credential")


def _validate_idempotency_key(supplied: str | None, expected: str) -> None:
    if supplied != expected:
        raise HTTPException(status_code=400, detail="Idempotency key mismatch")


app = create_app()
