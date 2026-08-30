import os
from uuid import uuid4

import httpx
import pytest
from distributed_agent_contracts import ContractStatus, WorkflowResponse

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 with Docker Compose running",
    ),
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_orchestrator_workflow_over_real_transports() -> None:
    expected_status = ContractStatus(os.getenv("EXPECTED_WORKFLOW_STATUS", "success"))
    request = {
        "request_id": str(uuid4()),
        "trace_id": "phase-3-compose-smoke",
        "query": "AI coding assistants",
    }

    async with httpx.AsyncClient() as client:
        first = await client.post("http://localhost:8000/workflows", json=request)
        second = await client.post("http://localhost:8000/workflows", json=request)

    default_http_status = 200 if expected_status is not ContractStatus.FAILED else 502
    expected_http_status = int(os.getenv("EXPECTED_WORKFLOW_HTTP_STATUS", default_http_status))
    assert first.status_code == expected_http_status
    assert second.status_code == expected_http_status
    first_response = WorkflowResponse.model_validate(first.json())
    second_response = WorkflowResponse.model_validate(second.json())
    assert first_response.status is expected_status
    assert second_response == first_response
    assert first_response.trace_id == request["trace_id"]
    assert (first_response.final_brief is not None) is (
        expected_status is not ContractStatus.FAILED
    )
