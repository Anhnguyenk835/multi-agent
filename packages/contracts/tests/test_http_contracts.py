from datetime import UTC, datetime
from uuid import uuid4

import pytest
from distributed_agent_contracts import (
    AnalysisRequest,
    Citation,
    ContractError,
    ContractStatus,
    ErrorCode,
    ExecutiveBrief,
    Finding,
    MarketAnalystInput,
    MarketAnalystOutput,
    Source,
    render_citation_links,
)
from pydantic import ValidationError


def metadata() -> dict[str, object]:
    return {
        "request_id": uuid4(),
        "trace_id": "trace-contract-test",
        "deadline_at": datetime.now(UTC),
    }


def finding() -> Finding:
    return Finding(
        title="Developer adoption",
        claim="Developers are adopting coding agents.",
        source=Source(
            title="Research source",
            url="https://example.com/research",
            publisher="Example Research",
            retrieved_at=datetime.now(UTC),
        ),
    )


def test_market_analyst_input_serializes_to_remote_state() -> None:
    request = MarketAnalystInput(query="AI coding agents", **metadata())

    payload = request.model_dump(mode="json")

    assert payload["contract_version"] == "v1"
    assert payload["query"] == "AI coding agents"
    assert isinstance(payload["request_id"], str)


def test_analysis_requires_at_least_one_upstream_result() -> None:
    with pytest.raises(ValidationError, match="requires research findings"):
        AnalysisRequest(query="AI coding agents", **metadata())


def test_analysis_accepts_valid_research_findings() -> None:
    request = AnalysisRequest(
        query="AI coding agents",
        research_findings=[finding()],
        **metadata(),
    )

    assert request.research_findings[0].source.publisher == "Example Research"


def test_successful_brief_requires_content() -> None:
    with pytest.raises(ValidationError, match="require content"):
        ExecutiveBrief(status=ContractStatus.SUCCESS, **metadata())


def test_degraded_response_allows_warnings_without_error() -> None:
    response = MarketAnalystOutput(
        status=ContractStatus.DEGRADED,
        findings=[finding()],
        warnings=["A market source was unavailable."],
        **metadata(),
    )

    assert response.error is None
    assert response.warnings == ["A market source was unavailable."]


def test_failed_response_requires_a_canonical_error_code() -> None:
    response = MarketAnalystOutput(
        status=ContractStatus.FAILED,
        error=ContractError(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message="Research provider did not respond.",
            retryable=True,
        ),
        **metadata(),
    )

    assert response.error is not None
    assert response.error.code is ErrorCode.UPSTREAM_UNAVAILABLE


def test_failed_response_rejects_unknown_error_code() -> None:
    with pytest.raises(ValidationError):
        MarketAnalystOutput(
            status=ContractStatus.FAILED,
            error={"code": "UNKNOWN_ERROR", "message": "Unsupported code"},
            **metadata(),
        )


def test_success_response_rejects_an_error_object() -> None:
    with pytest.raises(ValidationError, match="only failed responses"):
        MarketAnalystOutput(
            status=ContractStatus.SUCCESS,
            error=ContractError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Unexpected state",
            ),
            **metadata(),
        )


def test_source_metadata_rejects_invalid_url() -> None:
    with pytest.raises(ValidationError):
        Source(
            title="Research source",
            url="not-a-url",
            publisher="Example Research",
            retrieved_at=datetime.now(UTC),
        )


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MarketAnalystInput(query="AI coding agents", unexpected_field="value", **metadata())


def test_source_content_is_optional_and_uncapped() -> None:
    source = Source(
        title="Research source",
        url="https://example.com/research",
        publisher="Example Research",
        retrieved_at=datetime.now(UTC),
    )
    assert source.content is None

    long_content = "x" * 50_000
    source = Source(
        title="Research source",
        url="https://example.com/research",
        publisher="Example Research",
        retrieved_at=datetime.now(UTC),
        content=long_content,
    )
    assert source.content == long_content


def test_citation_has_no_content_field() -> None:
    assert "content" not in Citation.model_fields
    citation = Citation(
        title="Research source", url="https://example.com/research", publisher="Example Research"
    )
    assert str(citation.url) == "https://example.com/research"


def _citation(label: str) -> Citation:
    return Citation(
        title=f"{label} title", url=f"https://example.com/{label}", publisher=f"{label} publisher"
    )


def test_render_citation_links_resolves_known_markers() -> None:
    citations = [_citation("a"), _citation("b")]
    content = "Claim one [1]. Claim two [2]."

    linked = render_citation_links(content, citations)

    assert '[1](<https://example.com/a> "a title — a publisher")' in linked
    assert '[2](<https://example.com/b> "b title — b publisher")' in linked


def test_render_citation_links_escapes_title_special_characters() -> None:
    citation = Citation(
        title='AI Market Report (2026 Edition) "Preview"',
        url="https://example.com/report",
        publisher="Example",
    )

    linked = render_citation_links("Claim [1].", [citation])

    assert '\\"Preview\\"' in linked
    assert "Preview" in linked


def test_render_citation_links_leaves_out_of_range_markers_as_plain_text() -> None:
    linked = render_citation_links("Ungrounded claim [7].", [_citation("a")])

    assert "[7]." in linked
    assert "(https://" not in linked
