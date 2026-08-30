from dataclasses import dataclass

FIXTURE_TIME_UNIX_MS = 1_767_225_600_000


@dataclass(frozen=True)
class MarketFixture:
    market_signals: list[dict[str, object]]
    competitors: list[str]


def market_fixture(query: str) -> MarketFixture:
    subject = query.strip()
    source = {
        "title": "Deterministic developer tools market fixture",
        "url": "https://example.com/market/developer-tools",
        "publisher": "Demo Market Dataset",
        "published_at_unix_ms": FIXTURE_TIME_UNIX_MS,
        "retrieved_at_unix_ms": FIXTURE_TIME_UNIX_MS,
    }
    return MarketFixture(
        market_signals=[
            {
                "topic": "Platform integration",
                "observation": f"Buyers evaluating {subject} prioritize workflow integration.",
                "source": source,
            },
            {
                "topic": "Governance",
                "observation": "Enterprise adoption depends on access controls and auditability.",
                "source": source,
            },
        ],
        competitors=["GitHub Copilot", "Cursor", "Google Gemini Code Assist"],
    )
