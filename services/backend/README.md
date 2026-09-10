# Backend

FastAPI service for saved market intelligence and human report review.
PostgreSQL owns market identity, immutable report/draft/evidence snapshots,
conversation memory, review events, and source relationships.

## Local Docker

From the repository root:

```bash
docker compose up -d --build dashboard-postgres backend-migrate backend
```

The database is available on `localhost:54321` and the API on
`http://localhost:8010`. Migrations are serialized with a PostgreSQL advisory
lock, checksum validated, and applied by the one-shot `backend-migrate`
service before the API starts.

## Endpoints

```text
GET /health
GET /ready
GET /api/markets
GET /api/markets/{market_id}
GET /api/conversations/{conversation_id}/pending-review
POST /api/conversations/{conversation_id}/review-actions
POST /internal/markets/reports
POST /internal/report-drafts
POST /internal/report-drafts/publish
POST /internal/conversation-messages
GET /internal/conversations/{conversation_id}/review-context
```

The internal publication endpoint requires matching body/header idempotency
keys and, when configured, `Authorization: Bearer
${BACKEND_INTERNAL_API_TOKEN}`. One transaction persists evidence lineage,
publishes the report, and updates the Market's current report pointer.

Public review actions require `X-Actor-Id` and a matching body/header
`Idempotency-Key`. They are committed before delivery to the interrupted
LangGraph thread. `report_review_events` is also a transactional outbox: a
background dispatcher retries pending deliveries after backend restarts and
uses `review_event_id` metadata to avoid resuming the same decision twice.
