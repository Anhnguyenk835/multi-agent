import asyncio
import json
from datetime import datetime
from typing import Protocol

from distributed_agent_contracts import EvidenceFact, MarketAnalysisResponse, remaining_seconds
from langchain_core.messages import HumanMessage, SystemMessage

from market_analyst.llm import build_chat_model, model_timeouts
from market_analyst.market_models import MarketSynthesis, ResearchTask, ReviewAnswer, TaskExtraction
from market_analyst.market_prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    FOLLOWUP_SYSTEM_PROMPT,
    REVISION_SYSTEM_PROMPT,
    SYNTHESIS_SYSTEM_PROMPT,
)
from market_analyst.settings import MarketAnalystAISettings
from market_analyst.telemetry import _json_attribute, operation_span


class MarketModel(Protocol):
    async def extract(
        self,
        task: ResearchTask,
        sources: list[dict[str, object]],
        deadline_at: datetime | None,
    ) -> TaskExtraction: ...

    async def synthesize(
        self,
        *,
        market: dict[str, object],
        data_period: str,
        facts: list[EvidenceFact],
        source_ids: set[str],
        deadline_at: datetime | None,
    ) -> MarketSynthesis: ...

    async def revise(
        self,
        *,
        report: MarketAnalysisResponse,
        instruction: str,
        section_ids: list[str],
        facts: list[EvidenceFact],
        source_ids: set[str],
        context: dict[str, object],
        deadline_at: datetime | None,
    ) -> MarketSynthesis: ...

    async def answer_followup(
        self,
        *,
        report: MarketAnalysisResponse,
        question: str,
        facts: list[EvidenceFact],
        context: dict[str, object],
        deadline_at: datetime | None,
    ) -> ReviewAnswer: ...


class LiteLLMMarketModel:
    def __init__(self, settings: MarketAnalystAISettings) -> None:
        self._settings = settings

    async def extract(
        self,
        task: ResearchTask,
        sources: list[dict[str, object]],
        deadline_at: datetime | None,
    ) -> TaskExtraction:
        payload = {
            "task": task.model_dump(mode="json"),
            "sources": sources,
        }
        return await self._structured_call(
            operation_name="market_research.extract",
            schema=TaskExtraction,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            payload=payload,
            deadline_at=deadline_at,
            attributes={"app.research.dimension": task.dimension},
        )

    async def synthesize(
        self,
        *,
        market: dict[str, object],
        data_period: str,
        facts: list[EvidenceFact],
        source_ids: set[str],
        deadline_at: datetime | None,
    ) -> MarketSynthesis:
        payload = {
            "market": market,
            "data_period": data_period,
            "allowed_source_ids": sorted(source_ids),
            "facts": [fact.model_dump(mode="json") for fact in facts],
        }
        return await self._structured_call(
            operation_name="market_report.synthesize",
            schema=MarketSynthesis,
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
            payload=payload,
            deadline_at=deadline_at,
            attributes={"app.research.fact_count": len(facts)},
        )

    async def revise(
        self,
        *,
        report: MarketAnalysisResponse,
        instruction: str,
        section_ids: list[str],
        facts: list[EvidenceFact],
        source_ids: set[str],
        context: dict[str, object],
        deadline_at: datetime | None,
    ) -> MarketSynthesis:
        payload = {
            "instruction": instruction,
            "section_ids": section_ids,
            "current_report": report.model_dump(mode="json"),
            "allowed_source_ids": sorted(source_ids),
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "review_context": context,
        }
        return await self._structured_call(
            operation_name="market_report.revise",
            schema=MarketSynthesis,
            system_prompt=REVISION_SYSTEM_PROMPT,
            payload=payload,
            deadline_at=deadline_at,
            attributes={
                "app.research.fact_count": len(facts),
                "app.review.section_count": len(section_ids),
            },
        )

    async def answer_followup(
        self,
        *,
        report: MarketAnalysisResponse,
        question: str,
        facts: list[EvidenceFact],
        context: dict[str, object],
        deadline_at: datetime | None,
    ) -> ReviewAnswer:
        payload = {
            "question": question,
            "current_report": report.model_dump(mode="json"),
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "review_context": context,
        }
        return await self._structured_call(
            operation_name="market_report.answer_followup",
            schema=ReviewAnswer,
            system_prompt=FOLLOWUP_SYSTEM_PROMPT,
            payload=payload,
            deadline_at=deadline_at,
            attributes={"app.research.fact_count": len(facts)},
        )

    async def _structured_call(
        self,
        *,
        operation_name: str,
        schema,
        system_prompt: str,
        payload: dict[str, object],
        deadline_at: datetime | None,
        attributes: dict[str, object],
    ):
        remaining = remaining_seconds(deadline_at)
        if remaining is not None and remaining <= 2:
            raise TimeoutError(f"deadline reached before {operation_name}")

        gateway_timeout = None
        client_timeout = None
        if remaining is not None:
            gateway_timeout, client_timeout = model_timeouts(self._settings, remaining)
            if gateway_timeout <= 0 or client_timeout <= 0:
                raise TimeoutError(f"insufficient deadline budget for {operation_name}")

        model = build_chat_model(
            self._settings,
            timeout_seconds=client_timeout,
            gateway_timeout_seconds=gateway_timeout,
        ).with_structured_output(schema, method="function_calling")
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=json.dumps(payload, ensure_ascii=True, default=str)),
        ]
        with operation_span(
            operation_name,
            observation_type="agent",
            attributes={
                **attributes,
                "app.agent": "market_report_analyst",
                "langfuse.observation.input": _json_attribute(payload),
            },
        ) as span:
            if remaining is None:
                result = await model.ainvoke(messages)
            else:
                async with asyncio.timeout(max(1.0, remaining - 1.0)):
                    result = await model.ainvoke(messages)
            validated = schema.model_validate(result)
            span.set_attribute(
                "langfuse.observation.output",
                _json_attribute(validated.model_dump(mode="json")),
            )
            return validated
