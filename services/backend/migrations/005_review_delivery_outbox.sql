alter table report_review_events
    add column delivery_status text not null default 'submitted' check (
        delivery_status in ('pending', 'in_progress', 'submitted', 'failed')
    ),
    add column delivery_attempts integer not null default 0 check (delivery_attempts >= 0),
    add column delivery_error text,
    add column resume_run_id text,
    add column next_delivery_at timestamptz not null default now(),
    add column delivered_at timestamptz,
    add column delivery_updated_at timestamptz not null default now();

alter table report_review_events alter column delivery_status set default 'pending';

create index report_review_events_delivery_idx
    on report_review_events (next_delivery_at, created_at)
    where delivery_status in ('pending', 'failed', 'in_progress');
