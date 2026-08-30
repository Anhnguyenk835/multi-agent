import os
from uuid import uuid4

import httpx
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_AI_TESTS") != "1",
        reason="set RUN_LIVE_AI_TESTS=1 and provide real OPENAI_API_KEY/EXA_API_KEY to run",
    ),
]

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")


def test_live_query_returns_schema_valid_source_backed_brief() -> None:
    """Exit criterion for Phase 4: a real query against a docker-compose stack
    started with AI_MODE=live yields a schema-valid brief whose Researcher and
    Market findings/signals carry real Exa-derived sources."""

    payload = {
        "contract_version": "v1",
        "request_id": str(uuid4()),
        "trace_id": f"phase4-live-{uuid4()}",
        "attempt": 1,
        "query": "What are enterprises prioritizing when adopting AI coding agents in 2026?",
    }

    # Researcher/Market run in parallel (up to 90s each per orchestrator's
    # AgentPolicy), then Analyst and Writer run sequentially after (up to 40s
    # each) — budget comfortably above that worst case.
    response = httpx.post(f"{ORCHESTRATOR_URL}/workflows", json=payload, timeout=210)
    response.raise_for_status()
    body = response.json()

    assert body["status"] in {"success", "degraded"}
    brief = body["final_brief"]
    assert brief["content"]
    assert brief["citations"]
