from datetime import UTC, datetime

from distributed_agent_contracts import Finding, Source

FIXTURE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def build_findings(query: str) -> list[Finding]:
    return [
        Finding(
            title="Developer adoption trend",
            claim=f"Teams evaluating {query} prioritize measurable developer productivity.",
            source=Source(
                title="Deterministic research fixture",
                url="https://example.com/research/developer-adoption",
                publisher="Demo Research",
                published_at=FIXTURE_TIME,
                retrieved_at=FIXTURE_TIME,
            ),
        ),
        Finding(
            title="Integration requirements",
            claim="Adoption depends on IDE integration, governance, and review workflows.",
            source=Source(
                title="Deterministic integration fixture",
                url="https://example.com/research/integration-requirements",
                publisher="Demo Research",
                published_at=FIXTURE_TIME,
                retrieved_at=FIXTURE_TIME,
            ),
        ),
    ]
