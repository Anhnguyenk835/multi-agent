create extension if not exists pgcrypto;

create table workspaces (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table app_markets (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id),
    slug text not null,
    name text not null,
    definition text not null,
    scope jsonb not null,
    current_report_version integer,
    lock_version integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    archived_at timestamptz,
    unique (workspace_id, slug),
    check (slug = lower(slug)),
    check (current_report_version is null or current_report_version > 0),
    check (jsonb_typeof(scope) = 'object')
);

create table market_reports (
    id uuid primary key default gen_random_uuid(),
    market_id uuid not null references app_markets(id),
    version integer not null check (version > 0),
    schema_version text not null,
    status text not null check (status in ('partial', 'completed')),
    generated_at timestamptz not null,
    data_period text not null,
    overall_confidence smallint not null check (overall_confidence between 0 and 100),
    freshness text not null check (freshness in ('current', 'aging', 'stale')),
    warnings jsonb not null default '[]'::jsonb,
    overview jsonb not null,
    competitors jsonb not null,
    payload_hash text not null,
    published_at timestamptz not null default now(),
    unique (market_id, version),
    unique (market_id, payload_hash),
    check (jsonb_typeof(warnings) = 'array'),
    check (jsonb_typeof(overview) = 'object'),
    check (jsonb_typeof(competitors) = 'object')
);

alter table app_markets
    add constraint app_markets_current_report_fk
    foreign key (id, current_report_version)
    references market_reports(market_id, version)
    deferrable initially deferred;

create table evidence_sources (
    id uuid primary key default gen_random_uuid(),
    workspace_id uuid not null references workspaces(id),
    title text not null,
    publisher text not null,
    url text not null,
    published_at timestamptz,
    retrieved_at timestamptz not null,
    evidence_class text not null check (
        evidence_class in ('reported', 'estimated', 'derived', 'proxy', 'inferred')
    ),
    created_at timestamptz not null default now(),
    unique (workspace_id, url)
);

create table report_sources (
    report_id uuid not null references market_reports(id),
    public_id text not null,
    source_id uuid not null references evidence_sources(id),
    ordinal smallint not null check (ordinal > 0),
    primary key (report_id, public_id),
    unique (report_id, source_id),
    unique (report_id, ordinal)
);

create index app_markets_workspace_updated_idx
    on app_markets (workspace_id, updated_at desc)
    where archived_at is null;

create index market_reports_history_idx
    on market_reports (market_id, version desc);

create index report_sources_report_ordinal_idx
    on report_sources (report_id, ordinal);
