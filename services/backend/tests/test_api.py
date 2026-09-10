from datetime import UTC, datetime
from uuid import UUID, uuid4

from backend.config import BackendSettings
from backend.main import create_app
from backend.models import MarketAnalysisResponse, MarketSummary
from backend.repository import MarketNotFoundError
from distributed_agent_contracts import (
    ReportReviewDecision,
    ReportReviewEvent,
)
from fastapi.testclient import TestClient


class FakeRepository:
    def __init__(self) -> None:
        self.review_decisions: list[ReportReviewDecision] = []

    async def list_markets(self) -> list[MarketSummary]:
        return [
            MarketSummary(
                id="habit-tracking-apps",
                name="Habit Tracking Apps",
                definition="Consumer habit products.",
                momentum_score=64,
            )
        ]

    async def get_market(self, market_id: str) -> MarketAnalysisResponse:
        raise MarketNotFoundError(market_id)

    async def record_report_review(
        self, conversation_id: UUID, decision: ReportReviewDecision
    ) -> ReportReviewEvent:
        self.review_decisions.append(decision)
        return ReportReviewEvent(
            event_id=uuid4(),
            conversation_id=conversation_id,
            draft_id=decision.draft_id,
            review_generation=1,
            action=decision.action,
            status="approved" if decision.action == "approve_publish" else "in_review",
        )


class FakeReviewResumer:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, ReportReviewDecision]] = []

    async def resume(
        self, conversation_id: UUID, decision: ReportReviewDecision, event_id: UUID
    ) -> str:
        self.calls.append((conversation_id, decision))
        return "run-1"


def test_lists_markets() -> None:
    settings = BackendSettings(database_url="postgresql://unused", allowed_origins=())
    with TestClient(create_app(settings, FakeRepository())) as client:
        response = client.get("/api/markets")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "habit-tracking-apps",
            "name": "Habit Tracking Apps",
            "definition": "Consumer habit products.",
            "momentum_score": 64,
        }
    ]


def test_missing_market_returns_404() -> None:
    settings = BackendSettings(database_url="postgresql://unused", allowed_origins=())
    with TestClient(create_app(settings, FakeRepository())) as client:
        response = client.get("/api/markets/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Market not found"}


def test_review_action_uses_authenticated_actor_and_resumes_graph() -> None:
    repository = FakeRepository()
    resumer = FakeReviewResumer()
    settings = BackendSettings(
        database_url="postgresql://unused",
        allowed_origins=(),
        review_action_timeout_seconds=120,
    )
    conversation_id = uuid4()
    draft_id = uuid4()
    before = datetime.now(UTC)

    with TestClient(create_app(settings, repository, resumer)) as client:
        response = client.post(
            f"/api/conversations/{conversation_id}/review-actions",
            headers={"X-Actor-Id": "user-42", "Idempotency-Key": "approve-1"},
            json={
                "action": "approve_publish",
                "draft_id": str(draft_id),
                "expected_draft_hash": "a" * 64,
                "idempotency_key": "approve-1",
            },
        )

    assert response.status_code == 202
    decision = repository.review_decisions[0]
    assert decision.actor_id == "user-42"
    assert decision.action_deadline_at is not None
    assert 115 <= (decision.action_deadline_at - before).total_seconds() <= 125
    assert resumer.calls == [(conversation_id, decision)]


def test_review_action_requires_message_for_revision() -> None:
    settings = BackendSettings(database_url="postgresql://unused", allowed_origins=())
    with TestClient(create_app(settings, FakeRepository(), FakeReviewResumer())) as client:
        response = client.post(
            f"/api/conversations/{uuid4()}/review-actions",
            headers={"X-Actor-Id": "user-42", "Idempotency-Key": "revision-1"},
            json={
                "action": "request_revision",
                "draft_id": str(uuid4()),
                "expected_draft_hash": "a" * 64,
                "idempotency_key": "revision-1",
            },
        )

    assert response.status_code == 422
