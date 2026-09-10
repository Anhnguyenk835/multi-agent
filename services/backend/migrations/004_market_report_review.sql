create table conversations (
    id uuid primary key,
    active_run_id uuid references research_runs(id),
    status text not null default 'active' check (status in ('active', 'completed', 'cancelled')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table research_runs
    add column conversation_id uuid references conversations(id);

alter table research_runs drop constraint research_runs_status_check;
alter table research_runs add constraint research_runs_status_check check (
    status in (
        'running', 'awaiting_review', 'approved', 'completed', 'partial', 'failed', 'cancelled'
    )
);

create table conversation_messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations(id) on delete cascade,
    sequence integer not null check (sequence > 0),
    role text not null check (role in ('user', 'assistant', 'system')),
    kind text not null check (
        kind in (
            'user_question', 'assistant_answer', 'revision_request',
            'revision_summary', 'approval', 'system_event'
        )
    ),
    content jsonb not null,
    idempotency_key text not null,
    created_at timestamptz not null default now(),
    unique (conversation_id, sequence),
    unique (conversation_id, idempotency_key),
    check (jsonb_typeof(content) = 'object')
);

create table conversation_summaries (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations(id) on delete cascade,
    through_sequence integer not null default 0 check (through_sequence >= 0),
    summary jsonb not null,
    summary_version integer not null default 1 check (summary_version > 0),
    content_hash text not null,
    created_at timestamptz not null default now(),
    unique (conversation_id, summary_version),
    check (jsonb_typeof(summary) = 'object'),
    check (length(content_hash) = 64)
);

create table market_report_drafts (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references research_runs(id),
    conversation_id uuid not null references conversations(id),
    market_id uuid not null references app_markets(id),
    version integer not null check (version > 0),
    status text not null check (
        status in ('in_review', 'approved', 'published', 'superseded', 'cancelled')
    ),
    report jsonb not null,
    sources jsonb not null,
    facts jsonb not null,
    report_hash text not null,
    idempotency_key text not null,
    evidence_snapshot_id uuid references evidence_snapshots(id),
    based_on_draft_id uuid references market_report_drafts(id),
    review_generation integer not null check (review_generation > 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (run_id, version),
    unique (run_id, idempotency_key),
    check (jsonb_typeof(report) = 'object'),
    check (jsonb_typeof(sources) = 'array'),
    check (jsonb_typeof(facts) = 'array'),
    check (length(report_hash) = 64)
);

create unique index market_report_drafts_active_review_idx
    on market_report_drafts (run_id)
    where status in ('in_review', 'approved');

create table report_review_events (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations(id),
    draft_id uuid not null references market_report_drafts(id),
    review_generation integer not null check (review_generation > 0),
    actor_id text not null,
    action text not null check (
        action in (
            'ask_followup', 'request_revision', 'request_more_research',
            'approve_publish', 'cancel'
        )
    ),
    message text,
    section_ids jsonb not null default '[]'::jsonb,
    expected_draft_hash text not null,
    idempotency_key text not null,
    created_at timestamptz not null default now(),
    unique (conversation_id, idempotency_key),
    check (jsonb_typeof(section_ids) = 'array'),
    check (length(expected_draft_hash) = 64)
);

alter table market_reports
    add column draft_id uuid references market_report_drafts(id);

create unique index market_reports_draft_id_idx
    on market_reports (draft_id)
    where draft_id is not null;

create index conversation_messages_recent_idx
    on conversation_messages (conversation_id, sequence desc);

create index report_review_events_draft_idx
    on report_review_events (draft_id, created_at desc);
