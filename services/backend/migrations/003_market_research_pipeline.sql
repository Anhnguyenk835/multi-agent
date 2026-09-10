create table research_runs (
    id uuid primary key,
    idempotency_key text not null unique,
    market_id uuid references app_markets(id),
    status text not null check (status in ('running', 'completed', 'partial', 'failed')),
    published_report_id uuid references market_reports(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table research_tasks (
    id text primary key,
    run_id uuid not null references research_runs(id) on delete cascade,
    dimension text not null,
    status text not null check (status in ('pending', 'running', 'completed', 'partial', 'failed')),
    query_count integer not null default 0 check (query_count >= 0),
    source_count integer not null default 0 check (source_count >= 0),
    fact_count integer not null default 0 check (fact_count >= 0),
    warnings jsonb not null default '[]'::jsonb,
    updated_at timestamptz not null default now(),
    check (jsonb_typeof(warnings) = 'array')
);

create table source_snapshots (
    id uuid primary key default gen_random_uuid(),
    source_id uuid not null references evidence_sources(id),
    content_hash text not null,
    content_excerpt text not null,
    retrieved_at timestamptz not null,
    created_at timestamptz not null default now(),
    unique (source_id, content_hash),
    check (length(content_hash) = 64)
);

create table evidence_snapshots (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null unique references research_runs(id),
    market_id uuid not null references app_markets(id),
    status text not null check (status in ('sealed')),
    sealed_at timestamptz not null default now()
);

create table evidence_facts (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references research_runs(id),
    market_id uuid not null references app_markets(id),
    source_snapshot_id uuid not null references source_snapshots(id),
    dimension text not null,
    claim_type text not null,
    claim text not null,
    evidence_class text not null check (
        evidence_class in ('reported', 'estimated', 'derived', 'proxy', 'inferred')
    ),
    confidence smallint not null check (confidence between 0 and 100),
    numeric_value double precision,
    unit text,
    period text,
    claim_hash text not null,
    created_at timestamptz not null default now(),
    unique (run_id, claim_hash),
    check (length(claim_hash) = 64)
);

create table evidence_snapshot_facts (
    evidence_snapshot_id uuid not null references evidence_snapshots(id) on delete cascade,
    fact_id uuid not null references evidence_facts(id),
    primary key (evidence_snapshot_id, fact_id)
);

alter table market_reports
    add column run_id uuid references research_runs(id),
    add column evidence_snapshot_id uuid references evidence_snapshots(id);

create unique index market_reports_run_id_idx
    on market_reports (run_id)
    where run_id is not null;

create index research_tasks_run_idx on research_tasks (run_id, dimension);
create index source_snapshots_source_retrieved_idx on source_snapshots (source_id, retrieved_at desc);
create index evidence_facts_market_dimension_idx on evidence_facts (market_id, dimension);
