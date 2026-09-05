from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from distributed_agent_contracts import ContractStatus, ResearcherInput, ResearcherOutput
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolCall
from langchain_core.outputs import ChatGeneration, ChatResult
from researcher.errors import GroundingError, ToolCallLimitReachedError
from researcher.graph import _model_timeouts, build_graph, build_graph_for_settings
from researcher.settings import (
    DemoSettings,
    ResearcherAISettings,
    ResearcherExaSettings,
)


class _FakeToolCallingModel(BaseChatModel):
    """Minimal fake chat model that supports `.bind_tools()` and returns a
    pre-scripted sequence of messages, one per model call."""

    messages: list[BaseMessage] = []  # noqa: RUF012 - pydantic field, not a shared mutable default
    _index: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self.messages[self._index]
        self._index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "fake-tool-calling"


def _live_demo_settings() -> DemoSettings:
    return DemoSettings(
        ai=ResearcherAISettings(gateway_api_key="test-key"),
        exa=ResearcherExaSettings(exa_api_key="test-exa-key"),
    )


def _search_tool_call(call_id: str, query: str) -> AIMessage:
    return AIMessage(
        content="", tool_calls=[ToolCall(name="search", args={"query": query}, id=call_id)]
    )


def _final_findings_call(call_id: str, findings: list[dict[str, str]]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            ToolCall(name="LLMFindingsResponse", args={"findings": findings}, id=call_id)
        ],
    )


@pytest.mark.anyio
async def test_researcher_grounds_findings_in_tool_results(monkeypatch) -> None:
    import researcher.tools as tools_module

    class _FakeExaClient:
        async def search(self, query, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/live",
                        title="Live source",
                        published_date=None,
                        text="Teams are adopting AI coding agents rapidly.",
                    )
                ]
            )

    monkeypatch.setattr(tools_module, "_default_client_factory", lambda settings: _FakeExaClient())

    fake_model = _FakeToolCallingModel(
        messages=[
            _search_tool_call("call-1", "AI coding agents"),
            _final_findings_call(
                "call-2",
                [
                    {
                        "title": "Adoption",
                        "claim": "Teams adopt AI coding agents.",
                        "source_tag": "call-1#0",
                    }
                ],
            ),
        ]
    )
    monkeypatch.setattr("researcher.graph._build_chat_model", lambda settings: fake_model)

    request = ResearcherInput(request_id=uuid4(), trace_id="live-trace", query="AI coding agents")
    result = await build_graph_for_settings(_live_demo_settings()).ainvoke(
        request.model_dump(mode="json")
    )
    response = ResearcherOutput.model_validate(result)

    assert response.status is ContractStatus.SUCCESS
    assert len(response.findings) == 1
    assert response.findings[0].claim == "Teams adopt AI coding agents."
    assert str(response.findings[0].source.url) == "https://example.com/live"
    assert response.findings[0].source.publisher == "example.com"


@pytest.mark.anyio
async def test_researcher_rejects_unknown_source_tag(monkeypatch) -> None:
    import researcher.tools as tools_module

    class _FakeExaClient:
        async def search(self, query, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/live",
                        title="Live source",
                        published_date=None,
                        text="Some excerpt.",
                    )
                ]
            )

    monkeypatch.setattr(tools_module, "_default_client_factory", lambda settings: _FakeExaClient())

    fake_model = _FakeToolCallingModel(
        messages=[
            _search_tool_call("call-1", "AI coding agents"),
            _final_findings_call(
                "call-2",
                [{"title": "Bad", "claim": "Ungrounded claim.", "source_tag": "call-99#0"}],
            ),
        ]
    )
    monkeypatch.setattr("researcher.graph._build_chat_model", lambda settings: fake_model)

    request = ResearcherInput(request_id=uuid4(), trace_id="live-trace-2", query="AI coding agents")

    with pytest.raises(GroundingError):
        await build_graph_for_settings(_live_demo_settings()).ainvoke(request.model_dump(mode="json"))


@pytest.mark.anyio
async def test_researcher_raises_when_search_tool_call_limit_reached(monkeypatch) -> None:
    """Regression test: a 4th `search` call exceeds ToolCallLimitMiddleware's
    run_limit=3, which injects a plain-text (non-JSON) ToolMessage and jumps
    straight to END without a structured response. Both must be handled
    without crashing on a bare JSONDecodeError / AttributeError."""
    import researcher.tools as tools_module

    class _FakeExaClient:
        async def search(self, query, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/live",
                        title="Live source",
                        published_date=None,
                        text="Some excerpt.",
                    )
                ]
            )

    monkeypatch.setattr(tools_module, "_default_client_factory", lambda settings: _FakeExaClient())

    fake_model = _FakeToolCallingModel(
        messages=[
            _search_tool_call("call-1", "q1"),
            _search_tool_call("call-2", "q2"),
            _search_tool_call("call-3", "q3"),
            _search_tool_call("call-4", "q4"),  # exceeds run_limit=3
        ]
    )
    monkeypatch.setattr("researcher.graph._build_chat_model", lambda settings: fake_model)

    request = ResearcherInput(request_id=uuid4(), trace_id="limit-trace", query="AI coding agents")

    with pytest.raises(ToolCallLimitReachedError):
        await build_graph_for_settings(_live_demo_settings()).ainvoke(request.model_dump(mode="json"))


@pytest.mark.anyio
async def test_researcher_graph_factory_accepts_langgraph_server_config(monkeypatch) -> None:
    monkeypatch.setenv("LLM_GATEWAY_API_KEY", "test-key")

    fake_model = _FakeToolCallingModel(
        messages=[
            _search_tool_call("call-1", "AI coding agents"),
            _final_findings_call(
                "call-2",
                [
                    {
                        "title": "Adoption",
                        "claim": "Teams adopt AI coding agents.",
                        "source_tag": "call-1#0",
                    }
                ],
            ),
        ]
    )
    monkeypatch.setattr("researcher.graph._build_chat_model", lambda settings: fake_model)

    import researcher.tools as tools_module

    class _FakeExaClient:
        async def search(self, query, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/live",
                        title="Live source",
                        published_date=None,
                        text="Teams are adopting AI coding agents rapidly.",
                    )
                ]
            )

    monkeypatch.setattr(tools_module, "_default_client_factory", lambda settings: _FakeExaClient())
    request = ResearcherInput(
        request_id=uuid4(),
        trace_id="server-config-trace",
        query="AI coding agents",
    )

    result = await build_graph({"configurable": {"thread_id": "server-thread"}}).ainvoke(
        request.model_dump(mode="json")
    )

    assert ResearcherOutput.model_validate(result).status is ContractStatus.SUCCESS


@pytest.mark.anyio
async def test_expired_deadline_stops_before_model_or_tool_call(monkeypatch) -> None:
    fake_model = _FakeToolCallingModel(messages=[])
    monkeypatch.setattr("researcher.graph._build_chat_model", lambda settings: fake_model)
    request = ResearcherInput(
        request_id=uuid4(),
        trace_id="expired-deadline",
        deadline_at=datetime.now(UTC) - timedelta(seconds=1),
        query="AI coding agents",
    )

    result = await build_graph_for_settings(_live_demo_settings()).ainvoke(
        request.model_dump(mode="json")
    )
    response = ResearcherOutput.model_validate(result)

    assert response.status is ContractStatus.FAILED
    assert response.error is not None
    assert response.error.code.value == "DEADLINE_EXCEEDED"
    assert response.error.retryable is True
    assert fake_model._index == 0


def test_model_timeouts_fit_all_gateway_attempts_inside_remaining_budget() -> None:
    settings = ResearcherAISettings(
        gateway_api_key="test-key",
        llm_timeout_seconds=60,
        gateway_max_provider_attempts=4,
    )

    gateway_timeout, client_timeout = _model_timeouts(settings, remaining=85)

    assert gateway_timeout == pytest.approx(20.75)
    assert gateway_timeout * settings.gateway_max_provider_attempts == pytest.approx(83)
    assert client_timeout == pytest.approx(84)
