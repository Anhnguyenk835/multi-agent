from datetime import UTC, datetime

import pytest
from competitor_analyst.errors import InvalidOutputError
from competitor_analyst.models import (
    CompetitorProfileInput,
    CompetitorSynthesisInput,
    DiscoveryCandidateInput,
)
from competitor_analyst.tools import ExaSourceResult
from competitor_analyst.workflow import (
    EvidenceRegistry,
    build_analysis,
    ground_profile,
    select_competitors,
)


def _candidate(name: str, competitor_type: str) -> DiscoveryCandidateInput:
    return DiscoveryCandidateInput(
        name=name,
        type=competitor_type,
        rationale="Grounded candidate",
        source_tag="discovery#0",
    )


def test_select_competitors_deduplicates_and_prioritizes_direct() -> None:
    selected = select_competitors(
        [
            _candidate("Alternative", "substitute"),
            _candidate("Core App", "direct"),
            _candidate("core-app", "direct"),
        ],
        limit=2,
    )

    assert [(item.name, item.type) for item in selected] == [
        ("Core App", "direct"),
        ("Alternative", "substitute"),
    ]


def test_ground_profile_resolves_claim_tags_to_stable_source_ids() -> None:
    source = ExaSourceResult(
        tag="fc-1#0",
        title="Official product page",
        url="https://example.com/product/",
        publisher="example.com",
        published_at=None,
        retrieved_at=datetime(2026, 1, 2, tzinfo=UTC),
        content="The product supports recurring habit plans.",
    )
    structured = CompetitorProfileInput(
        name="Example",
        type="direct",
        positioning={"text": "Habit planning app", "source_tags": ["fc-1#0"]},
        platforms=[{"text": "Web", "source_tags": ["fc-1#0"]}],
        pricing={"model": "unknown"},
        features=[{"text": "Recurring plans", "source_tags": ["fc-1#0"]}],
        strengths=[{"text": "Focused workflow", "source_tags": ["fc-1#0"]}],
        weaknesses=[{"text": "Web only", "source_tags": ["fc-1#0"]}],
    )
    registry = EvidenceRegistry()

    profile = ground_profile(structured, {source.tag: source}, registry)

    assert profile.positioning.source_ids == [registry.values()[0].id]
    assert profile.source_ids == [registry.values()[0].id]
    assert profile.confidence > 50


def test_ground_profile_rejects_unknown_evidence_tag() -> None:
    structured = CompetitorProfileInput(
        name="Example",
        type="direct",
        positioning={"text": "Unsupported claim", "source_tags": ["missing#0"]},
        pricing={"model": "unknown"},
    )

    with pytest.raises(InvalidOutputError, match="unknown source tag"):
        ground_profile(structured, {}, EvidenceRegistry())


def test_synthesis_cannot_reference_evidence_outside_profiles() -> None:
    synthesis = CompetitorSynthesisInput(
        competition_level="moderate",
        market_structure="fragmented",
        feature_saturation="moderate",
        switching_cost="low",
        gaps=[
            {
                "segment": "Independent builders",
                "unmet_need": "Lower setup cost",
                "competitor_coverage": "low",
                "demand_strength": "moderate",
                "commercial_signal": "moderate",
                "source_ids": ["src_unknown"],
            }
        ],
    )

    with pytest.raises(InvalidOutputError, match="unknown source IDs"):
        build_analysis([], synthesis, EvidenceRegistry(), selected_count=1)
