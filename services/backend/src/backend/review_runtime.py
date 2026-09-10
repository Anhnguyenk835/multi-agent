import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import httpx
from distributed_agent_contracts import ReportReviewDecision

from backend.config import BackendSettings
from backend.repository import PendingReviewDelivery

logger = logging.getLogger(__name__)


class ReviewResumer(Protocol):
    async def resume(
        self, conversation_id: UUID, decision: ReportReviewDecision, event_id: UUID
    ) -> str: ...


class ReviewDeliveryStore(Protocol):
    async def claim_review_delivery(
        self, event_id: UUID | None = None
    ) -> PendingReviewDelivery | None: ...

    async def mark_review_delivery_submitted(self, event_id: UUID, run_id: str) -> None: ...

    async def mark_review_delivery_failed(self, event_id: UUID, error: str) -> None: ...


class LangGraphReviewResumer:
    def __init__(
        self,
        settings: BackendSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = settings.market_analyst_base_url
        self._assistant_id = settings.market_report_analyst_assistant_id
        self._transport = transport

    async def resume(
        self, conversation_id: UUID, decision: ReportReviewDecision, event_id: UUID
    ) -> str:
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=15.0, transport=self._transport
        ) as client:
            runs_response = await client.get(
                f"/threads/{conversation_id}/runs",
                params={"limit": 100},
            )
            runs_response.raise_for_status()
            event_key = str(event_id)
            for run in runs_response.json():
                if run.get("metadata", {}).get("review_event_id") == event_key:
                    return str(run["run_id"])
            response = await client.post(
                f"/threads/{conversation_id}/runs",
                json={
                    "assistant_id": self._assistant_id,
                    "command": {"resume": decision.model_dump(mode="json")},
                    "multitask_strategy": "reject",
                    "if_not_exists": "reject",
                    "durability": "sync",
                    "metadata": {
                        "review_event_id": event_key,
                        "review_idempotency_key": decision.idempotency_key,
                    },
                },
            )
            response.raise_for_status()
        return str(response.json()["run_id"])


class ReviewDispatcher:
    def __init__(
        self,
        store: ReviewDeliveryStore,
        resumer: ReviewResumer,
        *,
        action_timeout_seconds: int,
        poll_seconds: float = 1.0,
    ) -> None:
        self._store = store
        self._resumer = resumer
        self._action_timeout_seconds = action_timeout_seconds
        self._poll_seconds = poll_seconds
        self._stopping = asyncio.Event()

    async def dispatch(self, event_id: UUID | None = None) -> bool:
        delivery = await self._store.claim_review_delivery(event_id)
        if delivery is None:
            return False
        decision = delivery.decision.model_copy(
            update={
                "action_deadline_at": datetime.now(UTC)
                + timedelta(seconds=self._action_timeout_seconds)
            }
        )
        try:
            run_id = await self._resumer.resume(
                delivery.conversation_id, decision, delivery.event_id
            )
        except Exception as error:  # noqa: BLE001 - persisted outbox is retried by the worker
            await self._store.mark_review_delivery_failed(
                delivery.event_id, f"{type(error).__name__}: {error}"
            )
            return False
        await self._store.mark_review_delivery_submitted(delivery.event_id, run_id)
        return True

    async def run(self) -> None:
        while not self._stopping.is_set():
            try:
                delivered = await self.dispatch()
            except Exception:
                logger.exception("Review delivery polling failed")
                delivered = False
            if delivered:
                continue
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._poll_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stopping.set()
