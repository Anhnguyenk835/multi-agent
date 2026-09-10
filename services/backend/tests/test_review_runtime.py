from uuid import uuid4

import httpx
import pytest
from backend.config import BackendSettings
from backend.repository import PendingReviewDelivery
from backend.review_runtime import LangGraphReviewResumer, ReviewDispatcher
from distributed_agent_contracts import ReportReviewDecision


class FakeStore:
    def __init__(self, delivery: PendingReviewDelivery) -> None:
        self.delivery = delivery
        self.submitted: tuple[object, str] | None = None
        self.failed: tuple[object, str] | None = None

    async def claim_review_delivery(self, event_id=None):
        delivery, self.delivery = self.delivery, None
        return delivery

    async def mark_review_delivery_submitted(self, event_id, run_id) -> None:
        self.submitted = (event_id, run_id)

    async def mark_review_delivery_failed(self, event_id, error) -> None:
        self.failed = (event_id, error)


class FakeResumer:
    async def resume(self, conversation_id, decision, event_id) -> str:
        assert decision.action_deadline_at is not None
        return "langgraph-run-1"


@pytest.mark.anyio
async def test_dispatcher_delivers_persisted_review_action() -> None:
    event_id = uuid4()
    conversation_id = uuid4()
    delivery = PendingReviewDelivery(
        event_id=event_id,
        conversation_id=conversation_id,
        decision=ReportReviewDecision(
            action="approve_publish",
            draft_id=uuid4(),
            expected_draft_hash="a" * 64,
            idempotency_key="approve-1",
            actor_id="user-1",
        ),
    )
    store = FakeStore(delivery)

    delivered = await ReviewDispatcher(store, FakeResumer(), action_timeout_seconds=90).dispatch(
        event_id
    )

    assert delivered is True
    assert store.submitted == (event_id, "langgraph-run-1")
    assert store.failed is None


@pytest.mark.anyio
async def test_resumer_deduplicates_delivery_by_review_event_metadata() -> None:
    event_id = uuid4()
    conversation_id = uuid4()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "run_id": "existing-run",
                    "metadata": {"review_event_id": str(event_id)},
                }
            ],
        )

    resumer = LangGraphReviewResumer(
        BackendSettings(
            database_url="postgresql://unused",
            allowed_origins=(),
            market_analyst_base_url="http://market-analyst.test",
        ),
        transport=httpx.MockTransport(handler),
    )
    decision = ReportReviewDecision(
        action="approve_publish",
        draft_id=uuid4(),
        expected_draft_hash="a" * 64,
        idempotency_key="approve-1",
        actor_id="user-1",
    )

    run_id = await resumer.resume(conversation_id, decision, event_id)

    assert run_id == "existing-run"
    assert [request.method for request in requests] == ["GET"]
