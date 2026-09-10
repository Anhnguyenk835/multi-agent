insert into workspaces (id, name)
values ('10000000-0000-0000-0000-000000000001', 'Personal workspace');

insert into app_markets (
    id,
    workspace_id,
    slug,
    name,
    definition,
    scope
)
values (
    '20000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000001',
    'habit-tracking-apps',
    'Habit Tracking Apps',
    'Consumer apps that help individuals build and maintain recurring habits.',
    $json$
    {
      "geography": ["Global"],
      "platforms": ["iOS", "Android", "Web"],
      "customer_type": "B2C",
      "included": ["Habit tracking", "Streaks", "Reminders", "Accountability"],
      "excluded": ["Clinical treatment", "Enterprise wellness", "Project management"]
    }
    $json$::jsonb
);

insert into market_reports (
    id,
    market_id,
    version,
    schema_version,
    status,
    generated_at,
    data_period,
    overall_confidence,
    freshness,
    warnings,
    overview,
    competitors,
    payload_hash
)
values (
    '30000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    1,
    'market-analysis.v1',
    'completed',
    '2026-09-06T08:30:00Z',
    'Jan 2024 - Aug 2026',
    72,
    'current',
    '[]'::jsonb,
    $json$
    {
      "verdict": {
        "status": "selectively_attractive",
        "summary": "Demand remains strong, but the general-purpose segment is mature and highly commoditized.",
        "strengths": ["Persistent consumer demand", "Large mobile audience", "Established willingness to pay"],
        "constraints": ["High category churn", "Low switching costs", "Feature saturation"]
      },
      "scorecard": {
        "demand": 81,
        "market_size": 68,
        "momentum": 64,
        "commercial_quality": 59,
        "accessibility": 61,
        "competitive_headroom": 35
      },
      "market_size": {
        "metrics": [
          {
            "id": "annual_revenue",
            "label": "Estimated annual revenue",
            "range": {"min": 80000000, "max": 110000000},
            "unit": "USD",
            "period": "2025",
            "change": {"value": 18, "unit": "percent", "period": "YoY"},
            "evidence_class": "derived",
            "confidence": 68,
            "source_ids": ["src_01", "src_02"],
            "methodology": "Aggregated estimates for 25 tracked products"
          },
          {
            "id": "annual_downloads",
            "label": "Annual downloads",
            "value": 42000000,
            "unit": "downloads",
            "period": "2025",
            "change": {"value": 7, "unit": "percent", "period": "YoY"},
            "evidence_class": "estimated",
            "confidence": 74,
            "source_ids": ["src_02"]
          },
          {
            "id": "search_interest",
            "label": "Search demand index",
            "value": 67,
            "unit": "index",
            "period": "2026 YTD",
            "change": {"value": 16, "unit": "percent", "period": "YoY"},
            "evidence_class": "proxy",
            "confidence": 76,
            "source_ids": ["src_03"]
          }
        ],
        "revenue_history": [
          {"period": "2024", "value": 72000000, "unit": "USD", "evidence_class": "estimated", "confidence": 66, "source_ids": ["src_01", "src_02"]},
          {"period": "2025", "value": 95000000, "unit": "USD", "evidence_class": "derived", "confidence": 68, "source_ids": ["src_01", "src_02"]},
          {"period": "2026E", "value": 108000000, "unit": "USD", "evidence_class": "estimated", "confidence": 61, "source_ids": ["src_01", "src_02"]}
        ]
      },
      "momentum": {
        "direction": "growing",
        "strength": "moderate",
        "summary": "Estimated annual market revenue rises from $72M in 2024 to $108M in 2026.",
        "signals": [
          {"label": "Consumer spending", "change": 18, "unit": "percent", "period": "YoY", "source_ids": ["src_01"]},
          {"label": "Downloads", "change": 7, "unit": "percent", "period": "YoY", "source_ids": ["src_02"]},
          {"label": "Search interest", "change": 16, "unit": "percent", "period": "YoY", "source_ids": ["src_03"]}
        ]
      },
      "customer_segments": [
        {
          "id": "productivity-users",
          "name": "Productivity-focused professionals",
          "jobs": ["Maintain routines", "Track consistency", "Review progress"],
          "pain_points": ["Manual input fatigue", "Rigid streak systems"],
          "willingness_to_pay": "moderate",
          "confidence": 78,
          "source_ids": ["src_04"]
        },
        {
          "id": "adhd-users",
          "name": "ADHD and neurodivergent users",
          "jobs": ["Recover after missed days", "Reduce cognitive load", "Build flexible routines"],
          "pain_points": ["Punitive streak loss", "Overwhelming setup", "Notification fatigue"],
          "willingness_to_pay": "moderate",
          "confidence": 74,
          "source_ids": ["src_04", "src_06"]
        },
        {
          "id": "wellness-users",
          "name": "Wellness-oriented consumers",
          "jobs": ["Connect habits to wellbeing", "See long-term patterns"],
          "pain_points": ["Fragmented health data", "Weak actionable insight"],
          "willingness_to_pay": "low",
          "confidence": 66,
          "source_ids": ["src_04"]
        }
      ],
      "commercial_dynamics": {
        "dominant_model": "Freemium subscription",
        "typical_annual_price": {"min": 20, "max": 60, "unit": "USD"},
        "willingness_to_pay": "moderate",
        "retention_pressure": "high",
        "summary": "Subscription is validated, but habit abandonment limits customer lifetime value.",
        "source_ids": ["src_01", "src_04"]
      },
      "market_accessibility": {
        "level": "moderate",
        "channels": ["App Store search", "SEO", "Productivity communities", "Creator content"],
        "barriers": ["Crowded app-store keywords", "Strong incumbent reviews", "Low switching cost"],
        "summary": "The audience is reachable, but organic discovery is competitive.",
        "confidence": 70,
        "source_ids": ["src_03", "src_04"]
      },
      "risks": [
        {
          "id": "risk_01",
          "category": "Retention",
          "title": "High category churn",
          "probability": "high",
          "impact": "high",
          "summary": "Users frequently abandon tracking after initial motivation declines.",
          "source_ids": ["src_04"]
        },
        {
          "id": "risk_02",
          "category": "Competition",
          "title": "Feature commoditization",
          "probability": "high",
          "impact": "moderate",
          "summary": "Reminders, streaks, widgets, and basic analytics are widely available.",
          "source_ids": ["src_05"]
        },
        {
          "id": "risk_03",
          "category": "Distribution",
          "title": "Expensive mobile discovery",
          "probability": "moderate",
          "impact": "high",
          "summary": "Generic category keywords are dominated by established products.",
          "source_ids": ["src_03", "src_05"]
        }
      ],
      "opportunity_gaps": [
        {
          "id": "gap_01",
          "segment": "ADHD and neurodivergent users",
          "unmet_need": "Flexible habit recovery without streak-loss punishment.",
          "competitor_coverage": "low",
          "demand_strength": "high",
          "commercial_signal": "moderate",
          "confidence": 74,
          "source_ids": ["src_04", "src_06"]
        },
        {
          "id": "gap_02",
          "segment": "Small accountability groups",
          "unmet_need": "Private social accountability without a public community feed.",
          "competitor_coverage": "moderate",
          "demand_strength": "moderate",
          "commercial_signal": "moderate",
          "confidence": 69,
          "source_ids": ["src_04", "src_06"]
        },
        {
          "id": "gap_03",
          "segment": "Wellness-oriented consumers",
          "unmet_need": "Explain how routines correlate with sleep, energy, and mood.",
          "competitor_coverage": "low",
          "demand_strength": "moderate",
          "commercial_signal": "low",
          "confidence": 63,
          "source_ids": ["src_04", "src_05"]
        }
      ]
    }
    $json$::jsonb,
    $json$
    {
      "summary": {
        "competition_level": "high",
        "market_structure": "fragmented",
        "tracked_products": 25,
        "top_10_revenue_concentration": 64,
        "feature_saturation": "high",
        "switching_cost": "low",
        "source_ids": ["src_01", "src_02", "src_05"]
      },
      "items": [
        {
          "id": "habitica",
          "name": "Habitica",
          "type": "direct",
          "positioning": "Gamified habits and task management",
          "platforms": ["iOS", "Android", "Web"],
          "pricing": {"model": "Freemium", "annual_price": 47.99, "currency": "USD"},
          "strengths": ["Distinctive positioning", "Community mechanics"],
          "weaknesses": ["Complex interface", "Niche visual style"],
          "confidence": 86,
          "source_ids": ["src_07", "src_08"]
        },
        {
          "id": "streaks",
          "name": "Streaks",
          "type": "direct",
          "positioning": "Focused habit tracking for Apple users",
          "platforms": ["iOS", "macOS", "watchOS"],
          "pricing": {"model": "One-time purchase", "annual_price": null, "currency": "USD"},
          "strengths": ["Focused experience", "Deep Apple integration"],
          "weaknesses": ["Apple-only reach", "Rigid streak model"],
          "confidence": 82,
          "source_ids": ["src_07", "src_08"]
        },
        {
          "id": "productive",
          "name": "Productive",
          "type": "direct",
          "positioning": "Guided routines and habit programs",
          "platforms": ["iOS", "Android"],
          "pricing": {"model": "Subscription", "annual_price": 39.99, "currency": "USD"},
          "strengths": ["Polished onboarding", "Broad routine library"],
          "weaknesses": ["Aggressive paywall", "Generic recommendations"],
          "confidence": 79,
          "source_ids": ["src_07", "src_08"]
        }
      ]
    }
    $json$::jsonb,
    '16385d578d394ac862ccd3b98fc5f38e7e534807ea5d078a090c300c0afea95a'
);

insert into evidence_sources (
    id,
    workspace_id,
    title,
    publisher,
    url,
    published_at,
    retrieved_at,
    evidence_class
)
values
    ('40000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', 'Consumer spending estimate', 'Mobile intelligence provider', 'https://example.com/src_01', '2026-08-20', '2026-09-06T08:15:00Z', 'estimated'),
    ('40000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', 'Category download estimate', 'Mobile intelligence provider', 'https://example.com/src_02', '2026-08-20', '2026-09-06T08:15:00Z', 'estimated'),
    ('40000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', 'Habit tracking search interest', 'Search provider', 'https://example.com/src_03', '2026-08-20', '2026-09-06T08:15:00Z', 'proxy'),
    ('40000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000001', 'Customer review and pain-point analysis', 'Research dataset', 'https://example.com/src_04', '2026-08-20', '2026-09-06T08:15:00Z', 'derived'),
    ('40000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000001', 'Habit tracker feature landscape', 'Research dataset', 'https://example.com/src_05', '2026-08-20', '2026-09-06T08:15:00Z', 'derived'),
    ('40000000-0000-0000-0000-000000000006', '10000000-0000-0000-0000-000000000001', 'Underserved user segment discussions', 'Community dataset', 'https://example.com/src_06', '2026-08-20', '2026-09-06T08:15:00Z', 'proxy'),
    ('40000000-0000-0000-0000-000000000007', '10000000-0000-0000-0000-000000000001', 'Competitor product and pricing pages', 'Tracked competitors', 'https://example.com/src_07', '2026-08-20', '2026-09-06T08:15:00Z', 'reported'),
    ('40000000-0000-0000-0000-000000000008', '10000000-0000-0000-0000-000000000001', 'Competitor review summary', 'Review platform', 'https://example.com/src_08', '2026-08-20', '2026-09-06T08:15:00Z', 'derived');

insert into report_sources (report_id, public_id, source_id, ordinal)
values
    ('30000000-0000-0000-0000-000000000001', 'src_01', '40000000-0000-0000-0000-000000000001', 1),
    ('30000000-0000-0000-0000-000000000001', 'src_02', '40000000-0000-0000-0000-000000000002', 2),
    ('30000000-0000-0000-0000-000000000001', 'src_03', '40000000-0000-0000-0000-000000000003', 3),
    ('30000000-0000-0000-0000-000000000001', 'src_04', '40000000-0000-0000-0000-000000000004', 4),
    ('30000000-0000-0000-0000-000000000001', 'src_05', '40000000-0000-0000-0000-000000000005', 5),
    ('30000000-0000-0000-0000-000000000001', 'src_06', '40000000-0000-0000-0000-000000000006', 6),
    ('30000000-0000-0000-0000-000000000001', 'src_07', '40000000-0000-0000-0000-000000000007', 7),
    ('30000000-0000-0000-0000-000000000001', 'src_08', '40000000-0000-0000-0000-000000000008', 8);

update app_markets
set current_report_version = 1,
    lock_version = lock_version + 1,
    updated_at = now()
where id = '20000000-0000-0000-0000-000000000001';
