from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from competitor_analyst.agent import (
    SUBMIT_DISCOVERY_TOOL_NAME,
    SUBMIT_PROFILE_TOOL_NAME,
    SUBMIT_SYNTHESIS_TOOL_NAME,
    _DeadlineAwareCompletions,
    extract_submitted_model,
    submit_tool_names,
)
from competitor_analyst.models import CompetitorDiscoveryInput
from competitor_analyst.settings import CompetitorAISettings
from google.adk.events import Event
from google.adk.tools import FunctionTool
from google.genai import types


def test_submit_tool_names_match_adk_registration() -> None:
    expected = {
        SUBMIT_DISCOVERY_TOOL_NAME,
        SUBMIT_PROFILE_TOOL_NAME,
        SUBMIT_SYNTHESIS_TOOL_NAME,
    }
    assert {FunctionTool(function).name for function in submit_tool_names().values()} == expected


def test_extract_submitted_model_validates_typed_payload() -> None:
    event = Event(
        author="competitor_discovery",
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="fc-1",
                        name=SUBMIT_DISCOVERY_TOOL_NAME,
                        args={
                            "response": {
                                "candidates": [
                                    {
                                        "name": "Example",
                                        "type": "direct",
                                        "rationale": "Named in category roundup",
                                        "source_tag": "fc-search#0",
                                    }
                                ]
                            }
                        },
                    )
                )
            ],
        ),
    )

    output = extract_submitted_model(
        [event],
        tool_name=SUBMIT_DISCOVERY_TOOL_NAME,
        model_type=CompetitorDiscoveryInput,
    )

    assert output is not None
    assert output.candidates[0].name == "Example"


@pytest.mark.anyio
async def test_adk_model_turn_receives_remaining_gateway_budget() -> None:
    calls = []

    async def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace()

    adapter = _DeadlineAwareCompletions(
        SimpleNamespace(create=create),
        CompetitorAISettings(
            gateway_api_key="test-key",
            llm_timeout_seconds=60,
            gateway_max_provider_attempts=4,
        ),
        datetime.now(UTC) + timedelta(seconds=42),
    )

    await adapter.create(model="market-standard")

    assert 40 < calls[0]["timeout"] <= 41
    assert 9 < calls[0]["extra_body"]["request_timeout"] <= 10
