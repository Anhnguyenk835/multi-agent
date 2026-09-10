from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from writer.main import create_app
from writer.settings import DemoSettings, FailureMode


def request_payload() -> dict[str, object]:
    return {
        "contract_version": "v1",
        "request_id": str(uuid4()),
        "trace_id": "trace-phase-2",
        "attempt": 1,
        "query": "AI coding assistants",
        "analysis": "## Insights\n\n- Teams prioritize measurable productivity. [1]",
        "citations": [
            {
                "title": "Fixture",
                "url": "https://example.com/research",
                "publisher": "Demo Research",
            }
        ],
        "warnings": ["Fixture data only"],
    }


def test_invalid_payload_is_rejected() -> None:
    payload = request_payload()
    payload["contract_version"] = "v2"
    response = TestClient(create_app(DemoSettings())).post("/write", json=payload)

    assert response.status_code == 422


def test_transient_failure_is_contract_shaped_and_retryable() -> None:
    settings = DemoSettings(failure_mode=FailureMode.TRANSIENT_ERROR)
    response = TestClient(create_app(settings)).post("/write", json=request_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert response.json()["error"]["retryable"] is True


def test_expired_deadline_stops_before_writing() -> None:
    payload = request_payload()
    payload["deadline_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    response = TestClient(create_app(DemoSettings())).post("/write", json=payload)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "DEADLINE_EXCEEDED"


def test_write_uses_only_generated_content(monkeypatch) -> None:
    from writer import llm_client
    from writer.llm_schema import LLMBrief
    from writer.settings import WriterAISettings

    async def fake_generate_structured(*, schema, system_prompt, user_prompt, settings, **kwargs):
        assert schema is LLMBrief
        assert "[1] Fixture" in user_prompt
        return LLMBrief(content="# Live title\n\nLive summary citing [1].")

    monkeypatch.setattr(llm_client, "generate_structured", fake_generate_structured)

    settings = DemoSettings(ai=WriterAISettings(gateway_api_key="test-key"))
    response = TestClient(create_app(settings)).post("/write", json=request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == [
        {"title": "Fixture", "url": "https://example.com/research", "publisher": "Demo Research"}
    ]
    assert '[1](<https://example.com/research> "Fixture — Demo Research")' in body["content"]


def test_writer_prompt_never_includes_raw_research_fields() -> None:
    from distributed_agent_contracts import Citation, WriterRequest
    from writer.prompts import build_user_prompt

    assert "research_findings" not in WriterRequest.model_fields
    assert "competitive_signals" not in WriterRequest.model_fields
    assert "content" not in Citation.model_fields

    request = WriterRequest.model_validate(request_payload())
    prompt = build_user_prompt(request)

    assert "research_findings" not in prompt
    assert "competitive_signals" not in prompt
