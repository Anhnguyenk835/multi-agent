import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
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
    ReportReviewDecision,
    ReportReviewEvent,
)
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from backend.models import MarketAnalysisResponse, MarketSummary


class MarketNotFoundError(LookupError):
    pass


class PublicationConflictError(RuntimeError):
    pass


class DraftNotFoundError(LookupError):
    pass


class DraftConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PendingReviewDelivery:
    event_id: UUID
    conversation_id: UUID
    decision: ReportReviewDecision


class DashboardRepository:
    def __init__(self, pool: AsyncConnectionPool[Any]) -> None:
        self._pool = pool

    async def list_markets(self) -> list[MarketSummary]:
        query = """
            select
                market.slug as id,
                market.name,
                market.definition,
                (report.overview -> 'scorecard' ->> 'momentum')::smallint as momentum_score
            from app_markets market
            join market_reports report
              on report.market_id = market.id
             and report.version = market.current_report_version
            where market.archived_at is null
            order by market.name
        """
        async with (
            self._pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(query)
            rows = await cursor.fetchall()
        return [MarketSummary.model_validate(row) for row in rows]

    async def get_market(self, market_id: str) -> MarketAnalysisResponse:
        query = """
            select
                market.slug,
                market.name,
                market.definition,
                market.scope,
                report.id as report_id,
                report.version,
                report.schema_version,
                report.status,
                report.generated_at,
                report.data_period,
                report.overall_confidence,
                report.freshness,
                report.warnings,
                report.overview,
                report.competitors,
                coalesce(
                    (
                        select jsonb_agg(
                            jsonb_build_object(
                                'id', report_source.public_id,
                                'title', source.title,
                                'publisher', source.publisher,
                                'url', source.url,
                                'published_at', source.published_at,
                                'retrieved_at', source.retrieved_at,
                                'evidence_class', source.evidence_class
                            ) order by report_source.ordinal
                        )
                        from report_sources report_source
                        join evidence_sources source on source.id = report_source.source_id
                        where report_source.report_id = report.id
                    ),
                    '[]'::jsonb
                ) as evidence
            from app_markets market
            join market_reports report
              on report.market_id = market.id
             and report.version = market.current_report_version
            where market.slug = %s
              and market.archived_at is null
        """
        async with (
            self._pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            await cursor.execute(query, (market_id,))
            row = await cursor.fetchone()

        if row is None:
            raise MarketNotFoundError(market_id)

        return MarketAnalysisResponse.model_validate(
            {
                "schema_version": row["schema_version"],
                "market": {
                    "id": row["slug"],
                    "name": row["name"],
                    "definition": row["definition"],
                    "scope": row["scope"],
                },
                "report": {
                    "id": str(row["report_id"]),
                    "version": row["version"],
                    "status": row["status"],
                    "generated_at": row["generated_at"].isoformat(),
                    "data_period": row["data_period"],
                    "overall_confidence": row["overall_confidence"],
                    "freshness": row["freshness"],
                    "warnings": row["warnings"],
                },
                "overview": row["overview"],
                "competitors": row["competitors"],
                "evidence": row["evidence"],
            }
        )

    async def persist_market_report_draft(
        self,
        request: PersistMarketReportDraftRequest,
    ) -> MarketReportDraft:
        report_hash = _draft_hash(request)
        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (str(request.run_id),),
            )
            workspace_cursor = await connection.execute(
                "select id from workspaces order by created_at limit 1"
            )
            workspace_row = await workspace_cursor.fetchone()
            if workspace_row is None:
                raise RuntimeError("cannot persist a draft without a workspace")

            report = request.report
            market_cursor = await connection.execute(
                """
                insert into app_markets (workspace_id, slug, name, definition, scope)
                values (%s, %s, %s, %s, %s)
                on conflict (workspace_id, slug) do update set
                    name = excluded.name,
                    definition = excluded.definition,
                    scope = excluded.scope,
                    updated_at = now()
                returning id
                """,
                (
                    workspace_row[0],
                    report.market.id,
                    report.market.name,
                    report.market.definition,
                    Jsonb(report.market.scope.model_dump(mode="json")),
                ),
            )
            market_id = (await market_cursor.fetchone())[0]
            await connection.execute(
                """
                insert into conversations (id, status)
                values (%s, 'active')
                on conflict (id) do update set updated_at = now()
                """,
                (request.conversation_id,),
            )
            await connection.execute(
                """
                insert into research_runs (
                    id, idempotency_key, market_id, conversation_id, status
                ) values (%s, %s, %s, %s, 'awaiting_review')
                on conflict (id) do update set
                    market_id = excluded.market_id,
                    conversation_id = excluded.conversation_id,
                    status = case
                        when research_runs.published_report_id is null then 'awaiting_review'
                        else research_runs.status
                    end,
                    updated_at = now()
                """,
                (
                    request.run_id,
                    f"research-run:{request.run_id}",
                    market_id,
                    request.conversation_id,
                ),
            )
            await connection.execute(
                """
                update conversations
                set active_run_id = %s, updated_at = now()
                where id = %s
                """,
                (request.run_id, request.conversation_id),
            )

            duplicate_cursor = await connection.execute(
                """
                select id, version, status, report_hash, report, conversation_id
                from market_report_drafts
                where run_id = %s and idempotency_key = %s
                """,
                (request.run_id, request.idempotency_key),
            )
            duplicate = await duplicate_cursor.fetchone()
            if duplicate:
                if duplicate[3] != report_hash or duplicate[5] != request.conversation_id:
                    raise DraftConflictError(
                        "idempotency key was already used for a different draft payload"
                    )
                return MarketReportDraft.model_validate(
                    {
                        "draft_id": duplicate[0],
                        "run_id": request.run_id,
                        "conversation_id": request.conversation_id,
                        "version": duplicate[1],
                        "status": duplicate[2],
                        "report_hash": duplicate[3],
                        "report": duplicate[4],
                    }
                )

            if request.based_on_draft_id is not None:
                base_cursor = await connection.execute(
                    """
                    select 1 from market_report_drafts
                    where id = %s and run_id = %s and conversation_id = %s
                    """,
                    (
                        request.based_on_draft_id,
                        request.run_id,
                        request.conversation_id,
                    ),
                )
                if await base_cursor.fetchone() is None:
                    raise DraftConflictError("base draft does not belong to this research run")

            version_cursor = await connection.execute(
                """
                select coalesce(max(version), 0) + 1
                from market_report_drafts where run_id = %s
                """,
                (request.run_id,),
            )
            version = (await version_cursor.fetchone())[0]
            await connection.execute(
                """
                update market_report_drafts
                set status = 'superseded', updated_at = now()
                where run_id = %s and status in ('in_review', 'approved')
                """,
                (request.run_id,),
            )
            draft_cursor = await connection.execute(
                """
                insert into market_report_drafts (
                    run_id, conversation_id, market_id, version, status,
                    report, sources, facts, report_hash, based_on_draft_id,
                    review_generation, idempotency_key
                ) values (
                    %s, %s, %s, %s, 'in_review', %s, %s, %s, %s, %s, %s, %s
                ) returning id
                """,
                (
                    request.run_id,
                    request.conversation_id,
                    market_id,
                    version,
                    Jsonb(report.model_dump(mode="json")),
                    Jsonb([source.model_dump(mode="json") for source in request.sources]),
                    Jsonb([fact.model_dump(mode="json") for fact in request.facts]),
                    report_hash,
                    request.based_on_draft_id,
                    version,
                    request.idempotency_key,
                ),
            )
            draft_id = (await draft_cursor.fetchone())[0]
            await _upsert_review_summary(
                connection,
                request.conversation_id,
                objective=report.market.definition,
                draft_id=str(draft_id),
                draft_version=version,
            )
            return MarketReportDraft(
                draft_id=draft_id,
                run_id=request.run_id,
                conversation_id=request.conversation_id,
                version=version,
                status="in_review",
                report_hash=report_hash,
                report=report,
            )

    async def record_report_review(
        self,
        conversation_id: UUID,
        decision: ReportReviewDecision,
        *,
        delivery_confirmed: bool = False,
    ) -> ReportReviewEvent:
        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 1))",
                (str(conversation_id),),
            )
            duplicate_cursor = await connection.execute(
                """
                select
                    event.id,
                    event.draft_id,
                    event.review_generation,
                    event.action,
                    event.actor_id,
                    event.message,
                    event.section_ids,
                    event.expected_draft_hash,
                    draft.status
                from report_review_events event
                join market_report_drafts draft on draft.id = event.draft_id
                where event.conversation_id = %s and event.idempotency_key = %s
                """,
                (conversation_id, decision.idempotency_key),
            )
            duplicate = await duplicate_cursor.fetchone()
            if duplicate:
                persisted_payload = (
                    duplicate[1],
                    duplicate[3],
                    duplicate[4],
                    duplicate[5],
                    duplicate[6],
                    duplicate[7],
                )
                requested_payload = (
                    decision.draft_id,
                    decision.action,
                    decision.actor_id,
                    decision.message,
                    decision.section_ids,
                    decision.expected_draft_hash,
                )
                if persisted_payload != requested_payload:
                    raise DraftConflictError(
                        "idempotency key was already used for a different review action"
                    )
                if delivery_confirmed:
                    await connection.execute(
                        """
                        update report_review_events
                        set delivery_status = 'submitted',
                            delivered_at = coalesce(delivered_at, now()),
                            delivery_updated_at = now()
                        where id = %s
                        """,
                        (duplicate[0],),
                    )
                return ReportReviewEvent(
                    event_id=duplicate[0],
                    conversation_id=conversation_id,
                    draft_id=duplicate[1],
                    review_generation=duplicate[2],
                    action=duplicate[3],
                    status=duplicate[8],
                )

            draft_cursor = await connection.execute(
                """
                select report_hash, status, review_generation
                from market_report_drafts
                where id = %s and conversation_id = %s
                for update
                """,
                (decision.draft_id, conversation_id),
            )
            draft = await draft_cursor.fetchone()
            if draft is None:
                raise DraftNotFoundError(str(decision.draft_id))
            if draft[0] != decision.expected_draft_hash:
                raise DraftConflictError("draft hash is stale")
            if draft[1] != "in_review":
                raise DraftConflictError(f"draft is {draft[1]}, not in review")

            status = draft[1]
            if decision.action == "approve_publish":
                status = "approved"
            elif decision.action == "cancel":
                status = "cancelled"
            if status != draft[1]:
                await connection.execute(
                    """
                    update market_report_drafts set status = %s, updated_at = now()
                    where id = %s
                    """,
                    (status, decision.draft_id),
                )
            if decision.action in ("approve_publish", "cancel"):
                run_status = "approved" if decision.action == "approve_publish" else "cancelled"
                await connection.execute(
                    """
                    update research_runs set status = %s, updated_at = now()
                    where id = (select run_id from market_report_drafts where id = %s)
                    """,
                    (run_status, decision.draft_id),
                )
            if decision.action == "cancel":
                await connection.execute(
                    """
                    update conversations set status = 'cancelled', updated_at = now()
                    where id = %s
                    """,
                    (conversation_id,),
                )

            event_cursor = await connection.execute(
                """
                insert into report_review_events (
                    conversation_id, draft_id, review_generation, actor_id,
                    action, message, section_ids, expected_draft_hash, idempotency_key,
                    delivery_status, delivered_at
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    conversation_id,
                    decision.draft_id,
                    draft[2],
                    decision.actor_id,
                    decision.action,
                    decision.message,
                    Jsonb(decision.section_ids),
                    decision.expected_draft_hash,
                    decision.idempotency_key,
                    "submitted" if delivery_confirmed else "pending",
                    datetime.now(UTC) if delivery_confirmed else None,
                ),
            )
            event_id = (await event_cursor.fetchone())[0]
            if decision.message:
                kind = "user_question" if decision.action == "ask_followup" else "revision_request"
                await _append_message(
                    connection,
                    AppendConversationMessageRequest(
                        conversation_id=conversation_id,
                        role="user",
                        kind=kind,
                        content=decision.message,
                        idempotency_key=f"review-message:{decision.idempotency_key}",
                    ),
                )
            elif decision.action == "approve_publish":
                await _append_message(
                    connection,
                    AppendConversationMessageRequest(
                        conversation_id=conversation_id,
                        role="user",
                        kind="approval",
                        content=f"Approved draft {decision.draft_id}",
                        idempotency_key=f"review-message:{decision.idempotency_key}",
                    ),
                )
            await _update_summary_for_decision(connection, conversation_id, decision)
            return ReportReviewEvent(
                event_id=event_id,
                conversation_id=conversation_id,
                draft_id=decision.draft_id,
                review_generation=draft[2],
                action=decision.action,
                status=status,
            )

    async def claim_review_delivery(
        self, event_id: UUID | None = None
    ) -> PendingReviewDelivery | None:
        async with self._pool.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """
                select
                    id, conversation_id, draft_id, action, actor_id, message,
                    section_ids, expected_draft_hash, idempotency_key
                from report_review_events
                where (%s::uuid is null or id = %s)
                  and (
                    delivery_status in ('pending', 'failed')
                    or (
                        delivery_status = 'in_progress'
                        and delivery_updated_at < now() - interval '1 minute'
                    )
                  )
                  and next_delivery_at <= now()
                order by created_at
                for update skip locked
                limit 1
                """,
                (event_id, event_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            await connection.execute(
                """
                update report_review_events
                set delivery_status = 'in_progress',
                    delivery_attempts = delivery_attempts + 1,
                    delivery_error = null,
                    delivery_updated_at = now()
                where id = %s
                """,
                (row[0],),
            )
        return PendingReviewDelivery(
            event_id=row[0],
            conversation_id=row[1],
            decision=ReportReviewDecision(
                action=row[3],
                draft_id=row[2],
                expected_draft_hash=row[7],
                idempotency_key=row[8],
                message=row[5],
                section_ids=row[6],
                actor_id=row[4],
            ),
        )

    async def mark_review_delivery_submitted(self, event_id: UUID, run_id: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                update report_review_events
                set delivery_status = 'submitted', resume_run_id = %s,
                    delivered_at = now(), delivery_updated_at = now()
                where id = %s and delivery_status = 'in_progress'
                """,
                (run_id, event_id),
            )

    async def mark_review_delivery_failed(self, event_id: UUID, error: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                update report_review_events
                set delivery_status = 'failed', delivery_error = left(%s, 2000),
                    next_delivery_at = now() + interval '5 seconds',
                    delivery_updated_at = now()
                where id = %s and delivery_status = 'in_progress'
                """,
                (error, event_id),
            )

    async def append_conversation_message(
        self,
        request: AppendConversationMessageRequest,
    ) -> ConversationMessage:
        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 1))",
                (str(request.conversation_id),),
            )
            message, created = await _append_message(connection, request)
            if created and request.kind == "assistant_answer":
                await _update_summary_for_answer(
                    connection, request.conversation_id, request.content
                )
            return message

    async def get_review_context(
        self,
        conversation_id: UUID,
        *,
        message_limit: int = 12,
    ) -> ConversationReviewContext:
        async with self._pool.connection() as connection:
            summary_cursor = await connection.execute(
                """
                select summary from conversation_summaries
                where conversation_id = %s
                order by summary_version desc limit 1
                """,
                (conversation_id,),
            )
            summary_row = await summary_cursor.fetchone()
            message_cursor = await connection.execute(
                """
                select id, sequence, role, kind, content ->> 'text'
                from conversation_messages
                where conversation_id = %s
                order by sequence desc limit %s
                """,
                (conversation_id, message_limit),
            )
            rows = list(reversed(await message_cursor.fetchall()))
        return ConversationReviewContext(
            conversation_id=conversation_id,
            summary=summary_row[0] if summary_row else {},
            recent_messages=[
                ConversationMessage(
                    message_id=row[0],
                    conversation_id=conversation_id,
                    sequence=row[1],
                    role=row[2],
                    kind=row[3],
                    content=row[4],
                )
                for row in rows
            ],
        )

    async def get_pending_draft(self, conversation_id: UUID) -> MarketReportDraft:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                select id, run_id, conversation_id, version, status, report_hash, report
                from market_report_drafts
                where conversation_id = %s and status in ('in_review', 'approved')
                order by version desc limit 1
                """,
                (conversation_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            raise DraftNotFoundError(str(conversation_id))
        return MarketReportDraft.model_validate(
            {
                "draft_id": row[0],
                "run_id": row[1],
                "conversation_id": row[2],
                "version": row[3],
                "status": row[4],
                "report_hash": row[5],
                "report": row[6],
            }
        )

    async def publish_approved_draft(
        self,
        request: PublishApprovedMarketReportRequest,
    ) -> PublishMarketReportResponse:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                select run_id, report, sources, facts
                from market_report_drafts
                where id = %s and report_hash = %s and status in ('approved', 'published')
                """,
                (request.draft_id, request.expected_draft_hash),
            )
            row = await cursor.fetchone()
        if row is None:
            raise DraftConflictError("draft is missing, stale, or not approved")
        publication = PublishMarketReportRequest(
            run_id=row[0],
            idempotency_key=request.idempotency_key,
            report=row[1],
            sources=row[2],
            facts=row[3],
        )
        return await self.publish_market_report(
            publication,
            draft_id=request.draft_id,
            expected_draft_hash=request.expected_draft_hash,
        )

    async def publish_market_report(
        self,
        request: PublishMarketReportRequest,
        *,
        draft_id: UUID | None = None,
        expected_draft_hash: str | None = None,
    ) -> PublishMarketReportResponse:
        async with self._pool.connection() as connection, connection.transaction():
            await connection.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (str(request.run_id),),
            )
            if draft_id is not None:
                draft_cursor = await connection.execute(
                    """
                    select status, report_hash from market_report_drafts
                    where id = %s and run_id = %s for update
                    """,
                    (draft_id, request.run_id),
                )
                draft = await draft_cursor.fetchone()
                if (
                    draft is None
                    or draft[0] not in ("approved", "published")
                    or draft[1] != expected_draft_hash
                ):
                    raise DraftConflictError("draft approval is no longer valid")
            existing = await connection.execute(
                """
                select market.slug as market_id, report.id as report_id, report.version
                from research_runs run
                join market_reports report on report.id = run.published_report_id
                join app_markets market on market.id = report.market_id
                where run.id = %s
                """,
                (request.run_id,),
            )
            row = await existing.fetchone()
            if row:
                if draft_id is not None:
                    await connection.execute(
                        """
                        update market_report_drafts set status = 'published', updated_at = now()
                        where id = %s
                        """,
                        (draft_id,),
                    )
                return PublishMarketReportResponse(
                    market_id=row[0], report_id=str(row[1]), report_version=row[2]
                )

            workspace = await connection.execute(
                "select id from workspaces order by created_at limit 1"
            )
            workspace_row = await workspace.fetchone()
            if workspace_row is None:
                raise RuntimeError("cannot publish a market report without a workspace")
            workspace_id = workspace_row[0]
            report = request.report

            market_cursor = await connection.execute(
                """
                insert into app_markets (workspace_id, slug, name, definition, scope)
                values (%s, %s, %s, %s, %s)
                on conflict (workspace_id, slug) do update set
                    name = excluded.name,
                    definition = excluded.definition,
                    scope = excluded.scope,
                    updated_at = now()
                returning id
                """,
                (
                    workspace_id,
                    report.market.id,
                    report.market.name,
                    report.market.definition,
                    Jsonb(report.market.scope.model_dump(mode="json")),
                ),
            )
            market_id = (await market_cursor.fetchone())[0]
            await connection.execute(
                """
                insert into research_runs (id, idempotency_key, market_id, status)
                values (%s, %s, %s, 'running')
                on conflict (id) do nothing
                """,
                (request.run_id, f"research-run:{request.run_id}", market_id),
            )
            run_cursor = await connection.execute(
                "select idempotency_key from research_runs where id = %s",
                (request.run_id,),
            )
            persisted_key = (await run_cursor.fetchone())[0]
            if persisted_key != f"research-run:{request.run_id}":
                raise PublicationConflictError(
                    "research run already exists with a different idempotency key"
                )

            snapshot_cursor = await connection.execute(
                """
                insert into evidence_snapshots (run_id, market_id, status)
                values (%s, %s, 'sealed')
                on conflict (run_id) do update set status = excluded.status
                returning id
                """,
                (request.run_id, market_id),
            )
            evidence_snapshot_id = (await snapshot_cursor.fetchone())[0]
            source_ids: dict[str, tuple[object, object]] = {}
            for source in request.sources:
                evidence_class = _source_evidence_class(source.public_id, request)
                source_cursor = await connection.execute(
                    """
                    insert into evidence_sources (
                        workspace_id, title, publisher, url, published_at,
                        retrieved_at, evidence_class
                    ) values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (workspace_id, url) do update set
                        title = excluded.title,
                        publisher = excluded.publisher,
                        published_at = excluded.published_at,
                        retrieved_at = excluded.retrieved_at,
                        evidence_class = excluded.evidence_class
                    returning id
                    """,
                    (
                        workspace_id,
                        source.title,
                        source.publisher,
                        str(source.url),
                        source.published_at,
                        source.retrieved_at,
                        evidence_class,
                    ),
                )
                evidence_source_id = (await source_cursor.fetchone())[0]
                snapshot_source_cursor = await connection.execute(
                    """
                    insert into source_snapshots (
                        source_id, content_hash, content_excerpt, retrieved_at
                    ) values (%s, %s, %s, %s)
                    on conflict (source_id, content_hash) do update set
                        retrieved_at = excluded.retrieved_at
                    returning id
                    """,
                    (
                        evidence_source_id,
                        source.content_hash,
                        source.content_excerpt,
                        source.retrieved_at,
                    ),
                )
                source_snapshot_id = (await snapshot_source_cursor.fetchone())[0]
                source_ids[source.public_id] = (evidence_source_id, source_snapshot_id)

            for fact in request.facts:
                source_pair = source_ids.get(fact.source_id)
                if source_pair is None:
                    raise ValueError(f"fact references unknown source {fact.source_id!r}")
                claim_hash = _fact_hash(fact.model_dump(mode="json"))
                fact_cursor = await connection.execute(
                    """
                    insert into evidence_facts (
                        run_id, market_id, source_snapshot_id, dimension, claim_type,
                        claim, evidence_class, confidence, numeric_value, unit, period,
                        claim_hash
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (run_id, claim_hash) do update set claim = excluded.claim
                    returning id
                    """,
                    (
                        request.run_id,
                        market_id,
                        source_pair[1],
                        fact.dimension,
                        fact.claim_type,
                        fact.claim,
                        fact.evidence_class,
                        fact.confidence,
                        fact.numeric_value,
                        fact.unit,
                        fact.period,
                        claim_hash,
                    ),
                )
                fact_id = (await fact_cursor.fetchone())[0]
                await connection.execute(
                    """
                    insert into evidence_snapshot_facts (evidence_snapshot_id, fact_id)
                    values (%s, %s) on conflict do nothing
                    """,
                    (evidence_snapshot_id, fact_id),
                )

            payload_hash = _fact_hash(
                {
                    "report": report.model_dump(mode="json"),
                    "source_hashes": sorted(source.content_hash for source in request.sources),
                }
            )
            duplicate_cursor = await connection.execute(
                """
                select id, version from market_reports
                where market_id = %s and payload_hash = %s
                """,
                (market_id, payload_hash),
            )
            duplicate = await duplicate_cursor.fetchone()
            if duplicate:
                report_id, report_version = duplicate
            else:
                version_cursor = await connection.execute(
                    "select coalesce(max(version), 0) + 1 from market_reports where market_id = %s",
                    (market_id,),
                )
                report_version = (await version_cursor.fetchone())[0]
                report_cursor = await connection.execute(
                    """
                    insert into market_reports (
                        market_id, version, schema_version, status, generated_at,
                        data_period, overall_confidence, freshness, warnings,
                        overview, competitors, payload_hash, run_id, evidence_snapshot_id,
                        draft_id
                    ) values (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) returning id
                    """,
                    (
                        market_id,
                        report_version,
                        report.schema_version,
                        report.report.status,
                        report.report.generated_at,
                        report.report.data_period,
                        report.report.overall_confidence,
                        report.report.freshness,
                        Jsonb(report.report.warnings),
                        Jsonb(report.overview.model_dump(mode="json")),
                        Jsonb(report.competitors.model_dump(mode="json")),
                        payload_hash,
                        request.run_id,
                        evidence_snapshot_id,
                        draft_id,
                    ),
                )
                report_id = (await report_cursor.fetchone())[0]

                for ordinal, evidence in enumerate(report.evidence, start=1):
                    source_pair = source_ids.get(evidence.id)
                    if source_pair is None:
                        raise ValueError(f"report references unknown source {evidence.id!r}")
                    await connection.execute(
                        """
                        insert into report_sources (report_id, public_id, source_id, ordinal)
                        values (%s, %s, %s, %s)
                        """,
                        (report_id, evidence.id, source_pair[0], ordinal),
                    )

            await connection.execute(
                """
                update app_markets
                set current_report_version = %s, updated_at = now()
                where id = %s
                """,
                (report_version, market_id),
            )
            await connection.execute(
                """
                update research_runs
                set status = %s, published_report_id = %s, updated_at = now()
                where id = %s
                """,
                (report.report.status, report_id, request.run_id),
            )
            if draft_id is not None:
                await connection.execute(
                    """
                    update market_report_drafts set status = 'published', updated_at = now()
                    where id = %s
                    """,
                    (draft_id,),
                )
                await connection.execute(
                    """
                    update conversations set status = 'completed', updated_at = now()
                    where active_run_id = %s
                    """,
                    (request.run_id,),
                )
            return PublishMarketReportResponse(
                market_id=report.market.id,
                report_id=str(report_id),
                report_version=report_version,
            )


def _fact_hash(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _draft_hash(request: PersistMarketReportDraftRequest) -> str:
    return _fact_hash(
        {
            "report": request.report.model_dump(mode="json"),
            "sources": [source.model_dump(mode="json") for source in request.sources],
            "facts": [fact.model_dump(mode="json") for fact in request.facts],
        }
    )


async def _append_message(
    connection, request: AppendConversationMessageRequest
) -> tuple[ConversationMessage, bool]:
    existing = await connection.execute(
        """
        select id, sequence, role, kind, content ->> 'text'
        from conversation_messages
        where conversation_id = %s and idempotency_key = %s
        """,
        (request.conversation_id, request.idempotency_key),
    )
    row = await existing.fetchone()
    if row:
        if (row[2], row[3], row[4]) != (request.role, request.kind, request.content):
            raise DraftConflictError(
                "idempotency key was already used for a different conversation message"
            )
        return (
            ConversationMessage(
                message_id=row[0],
                conversation_id=request.conversation_id,
                sequence=row[1],
                role=request.role,
                kind=request.kind,
                content=request.content,
            ),
            False,
        )
    sequence_cursor = await connection.execute(
        """
        select coalesce(max(sequence), 0) + 1
        from conversation_messages where conversation_id = %s
        """,
        (request.conversation_id,),
    )
    sequence = (await sequence_cursor.fetchone())[0]
    message_cursor = await connection.execute(
        """
        insert into conversation_messages (
            conversation_id, sequence, role, kind, content, idempotency_key
        ) values (%s, %s, %s, %s, %s, %s)
        returning id
        """,
        (
            request.conversation_id,
            sequence,
            request.role,
            request.kind,
            Jsonb({"text": request.content}),
            request.idempotency_key,
        ),
    )
    return (
        ConversationMessage(
            message_id=(await message_cursor.fetchone())[0],
            conversation_id=request.conversation_id,
            sequence=sequence,
            role=request.role,
            kind=request.kind,
            content=request.content,
        ),
        True,
    )


async def _upsert_review_summary(
    connection,
    conversation_id,
    *,
    objective: str,
    draft_id: str,
    draft_version: int,
) -> None:
    cursor = await connection.execute(
        """
        select through_sequence, summary, summary_version
        from conversation_summaries
        where conversation_id = %s
        order by summary_version desc limit 1
        """,
        (conversation_id,),
    )
    row = await cursor.fetchone()
    summary = (
        dict(row[1])
        if row
        else {
            "objective": objective,
            "accepted_decisions": [],
            "answered_questions": [],
            "rejected_assumptions": [],
            "requested_changes": [],
            "unresolved_questions": [],
            "scope_constraints": {},
            "evidence_gaps": [],
        }
    )
    summary["current_draft"] = {"id": draft_id, "version": draft_version}
    version = (row[2] + 1) if row else 1
    through_sequence = row[0] if row else 0
    encoded_hash = _fact_hash(summary)
    await connection.execute(
        """
        insert into conversation_summaries (
            conversation_id, through_sequence, summary, summary_version, content_hash
        ) values (%s, %s, %s, %s, %s)
        """,
        (conversation_id, through_sequence, Jsonb(summary), version, encoded_hash),
    )


async def _update_summary_for_decision(connection, conversation_id, decision) -> None:
    cursor = await connection.execute(
        """
        select through_sequence, summary, summary_version
        from conversation_summaries
        where conversation_id = %s
        order by summary_version desc limit 1
        """,
        (conversation_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return
    summary = dict(row[1])
    if decision.action == "ask_followup" and decision.message:
        questions = list(summary.get("unresolved_questions", []))
        summary["unresolved_questions"] = (questions + [decision.message])[-20:]
    elif decision.action in ("request_revision", "request_more_research"):
        changes = list(summary.get("requested_changes", []))
        if decision.message:
            changes.append(decision.message)
        summary["requested_changes"] = changes[-20:]
    elif decision.action == "approve_publish":
        accepted = list(summary.get("accepted_decisions", []))
        accepted.append(f"Approved draft {decision.draft_id}")
        summary["accepted_decisions"] = accepted[-20:]
    version = row[2] + 1
    sequence_cursor = await connection.execute(
        "select coalesce(max(sequence), 0) from conversation_messages where conversation_id = %s",
        (conversation_id,),
    )
    through_sequence = (await sequence_cursor.fetchone())[0]
    await connection.execute(
        """
        insert into conversation_summaries (
            conversation_id, through_sequence, summary, summary_version, content_hash
        ) values (%s, %s, %s, %s, %s)
        """,
        (conversation_id, through_sequence, Jsonb(summary), version, _fact_hash(summary)),
    )


async def _update_summary_for_answer(connection, conversation_id, answer: str) -> None:
    cursor = await connection.execute(
        """
        select through_sequence, summary, summary_version
        from conversation_summaries
        where conversation_id = %s
        order by summary_version desc limit 1
        """,
        (conversation_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return
    summary = dict(row[1])
    questions = list(summary.get("unresolved_questions", []))
    question = questions.pop() if questions else None
    summary["unresolved_questions"] = questions
    answered = list(summary.get("answered_questions", []))
    answered.append({"question": question, "answer": answer})
    summary["answered_questions"] = answered[-20:]
    sequence_cursor = await connection.execute(
        "select coalesce(max(sequence), 0) from conversation_messages where conversation_id = %s",
        (conversation_id,),
    )
    through_sequence = (await sequence_cursor.fetchone())[0]
    await connection.execute(
        """
        insert into conversation_summaries (
            conversation_id, through_sequence, summary, summary_version, content_hash
        ) values (%s, %s, %s, %s, %s)
        """,
        (conversation_id, through_sequence, Jsonb(summary), row[2] + 1, _fact_hash(summary)),
    )


def _source_evidence_class(
    source_id: str,
    request: PublishMarketReportRequest,
) -> str:
    for fact in request.facts:
        if fact.source_id == source_id:
            return fact.evidence_class
    return "inferred"
