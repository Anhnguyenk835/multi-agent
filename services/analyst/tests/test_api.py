from datetime import UTC, datetime, timedelta
from uuid import uuid4

from analyst.main import create_app
from analyst.settings import DemoSettings, FailureMode
from fastapi.testclient import TestClient


def request_payload() -> dict[str, object]:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    return {
        "contract_version": "v1",
        "request_id": str(uuid4()),
        "trace_id": "trace-phase-2",
        "attempt": 1,
        "query": "AI coding assistants",
        "research_findings": [
            {
                "title": "Adoption",
                "claim": "Teams prioritize measurable productivity.",
                "source": {
                    "title": "Fixture",
                    "url": "https://example.com/research",
                    "publisher": "Demo Research",
                    "retrieved_at": timestamp,
                },
            }
        ],
        "competitive_signals": [],
        "competitors": ["Example Competitor"],
    }


def test_invalid_payload_is_rejected_before_chain() -> None:
    payload = request_payload()
    payload["research_findings"] = []
    response = TestClient(create_app(DemoSettings())).post("/analyze", json=payload)

    assert response.status_code == 422


def test_transient_failure_is_contract_shaped_and_retryable() -> None:
    settings = DemoSettings(failure_mode=FailureMode.TRANSIENT_ERROR)
    response = TestClient(create_app(settings)).post("/analyze", json=request_payload())

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "UPSTREAM_UNAVAILABLE",
        "message": "injected transient Analyst failure",
        "retryable": True,
    }


def test_expired_deadline_stops_before_analysis() -> None:
    payload = request_payload()
    payload["deadline_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    response = TestClient(create_app(DemoSettings())).post("/analyze", json=payload)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "DEADLINE_EXCEEDED"


def test_analyze_uses_only_generated_content(monkeypatch) -> None:
    from analyst import llm_client
    from analyst.llm_schema import LLMAnalysis
    from analyst.settings import AnalystAISettings

    async def fake_generate_structured(*, schema, system_prompt, user_prompt, settings, **kwargs):
        assert schema is LLMAnalysis
        assert "[1] Adoption" in user_prompt
        return LLMAnalysis(content="## Insights\n\n- Live insight [1]")

    monkeypatch.setattr(llm_client, "generate_structured", fake_generate_structured)

    settings = DemoSettings(ai=AnalystAISettings(gateway_api_key="test-key"))
    client = TestClient(create_app(settings))
    response = client.post("/analyze", json=request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == [
        {"title": "Fixture", "url": "https://example.com/research", "publisher": "Demo Research"}
    ]
    assert '[1](<https://example.com/research> "Fixture — Demo Research")' in body["content"]
