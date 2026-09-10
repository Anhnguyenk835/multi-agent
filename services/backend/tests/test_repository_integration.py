import hashlib
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from backend.repository import DashboardRepository
from distributed_agent_contracts import (
    AppendConversationMessageRequest,
    EvidenceFact,
    PersistMarketReportDraftRequest,
    PublishApprovedMarketReportRequest,
    ReportReviewDecision,
    SourceSnapshot,
)
from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.getenv("BACKEND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="integration database not configured")


@pytest.mark.anyio
async def test_review_memory_and_approved_publication_are_transactional() -> None:
    pool = AsyncConnectionPool(DATABASE_URL, open=False)
    await pool.open()
    try:
        repository = DashboardRepository(pool)
        seeded = await repository.get_market("habit-tracking-apps")
        run_id = uuid4()
        conversation_id = uuid4()
        market_id = f"review-test-{run_id.hex[:10]}"
        report = seeded.model_copy(
            update={
                "market": seeded.market.model_copy(
                    update={"id": market_id, "name": "Review Test Market"}
                ),
                "report": seeded.report.model_copy(update={"id": str(run_id), "version": 1}),
            }
        )
        snapshots = [
            SourceSnapshot(
                public_id=source.id,
                title=source.title,
                publisher=source.publisher,
                url=source.url,
                published_at=source.published_at,
                retrieved_at=datetime.now(UTC).isoformat(),
                content_hash=hashlib.sha256(str(source.url).encode()).hexdigest(),
                content_excerpt=f"Evidence snapshot for {source.title}",
            )
            for source in report.evidence
        ]
        dimensions = [
            "market_size",
            "momentum",
            "customers",
            "commercial",
            "accessibility",
            "competitors",
            "risks_opportunities",
        ]
        facts = [
            EvidenceFact(
                source_id=snapshot.public_id,
                dimension=dimensions[index % len(dimensions)],
                claim_type="integration_test",
                claim=f"Grounded test fact {index}",
                evidence_class="reported",
                confidence=80,
            )
            for index, snapshot in enumerate(snapshots)
        ]
        draft = await repository.persist_market_report_draft(
            PersistMarketReportDraftRequest(
                run_id=run_id,
                conversation_id=conversation_id,
                idempotency_key="draft-1",
                report=report.model_dump(mode="json"),
                sources=snapshots,
                facts=facts,
            )
        )

        question = ReportReviewDecision(
            action="ask_followup",
            draft_id=draft.draft_id,
            expected_draft_hash=draft.report_hash,
            idempotency_key="question-1",
            actor_id="integration-user",
            message="What is the strongest signal?",
        )
        first_event = await repository.record_report_review(conversation_id, question)
        duplicate_event = await repository.record_report_review(conversation_id, question)
        assert duplicate_event.event_id == first_event.event_id

        await repository.append_conversation_message(
            AppendConversationMessageRequest(
                conversation_id=conversation_id,
                role="assistant",
                kind="assistant_answer",
                content="The revenue trend is the strongest signal.",
                idempotency_key="answer-1",
            )
        )
        context = await repository.get_review_context(conversation_id)
        assert context.summary["unresolved_questions"] == []
        assert context.summary["answered_questions"][-1]["question"] == question.message

        await repository.record_report_review(
            conversation_id,
            ReportReviewDecision(
                action="approve_publish",
                draft_id=draft.draft_id,
                expected_draft_hash=draft.report_hash,
                idempotency_key="approve-1",
                actor_id="integration-user",
            ),
        )
        publication_request = PublishApprovedMarketReportRequest(
            draft_id=draft.draft_id,
            expected_draft_hash=draft.report_hash,
            idempotency_key="publish-1",
        )
        publication = await repository.publish_approved_draft(publication_request)
        duplicate_publication = await repository.publish_approved_draft(publication_request)

        assert publication == duplicate_publication
        assert publication.market_id == market_id
        assert (await repository.get_market(market_id)).market.id == market_id
    finally:
        await pool.close()
