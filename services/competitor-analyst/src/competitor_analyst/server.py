import asyncio
from datetime import UTC, datetime

import grpc
from distributed_agent_contracts import remaining_seconds
from distributed_agent_contracts.competitor.v1 import competitor_pb2, competitor_pb2_grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from competitor_analyst.errors import (
    InvalidOutputError,
    ProviderConfigurationError,
    ProviderUnavailableError,
)
from competitor_analyst.runner import CompetitorAnalystRunner
from competitor_analyst.settings import DemoSettings, FailureMode
from competitor_analyst.telemetry import (
    request_span,
    set_observation_input,
    set_observation_output,
)


class CompetitorAnalystService(competitor_pb2_grpc.CompetitorAnalystServicer):
    def __init__(
        self,
        runner: CompetitorAnalystRunner | None = None,
        settings: DemoSettings | None = None,
    ) -> None:
        self._settings = settings or DemoSettings.from_environment()
        self._runner = runner or CompetitorAnalystRunner(settings=self._settings)

    async def AnalyzeCompetitors(self, request, context):
        metadata = request.metadata
        if (
            metadata.contract_version != "v1"
            or not metadata.request_id
            or not metadata.trace_id
            or metadata.attempt < 1
            or not request.query.strip()
        ):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid competitor request")

        deadline_at = _deadline_from_unix_ms(metadata.deadline_unix_ms)
        try:
            remaining = remaining_seconds(deadline_at)
            if remaining is None:
                result = await self._analyze(request, context, deadline_at)
            else:
                if remaining <= 0:
                    raise TimeoutError
                async with asyncio.timeout(remaining):
                    result = await self._analyze(request, context, deadline_at)
        except TimeoutError:
            return _failure_response(
                metadata,
                competitor_pb2.ERROR_CODE_DEADLINE_EXCEEDED,
                "Competitor Analyst deadline exceeded",
                retryable=True,
            )
        except ProviderConfigurationError:
            return _failure_response(
                metadata,
                competitor_pb2.ERROR_CODE_INTERNAL_ERROR,
                "Competitor Analyst provider configuration is invalid",
                retryable=False,
            )
        except ProviderUnavailableError:
            return _failure_response(
                metadata,
                competitor_pb2.ERROR_CODE_UPSTREAM_UNAVAILABLE,
                "Competitor Analyst LLM provider is unavailable",
                retryable=True,
            )
        except InvalidOutputError:
            return _failure_response(
                metadata,
                competitor_pb2.ERROR_CODE_UPSTREAM_INVALID_RESPONSE,
                "Competitor Analyst returned invalid structured output",
                retryable=False,
            )
        if result is None:
            return competitor_pb2.CompetitorAnalysisResponse(
                metadata=metadata,
                status=competitor_pb2.RESPONSE_STATUS_UNSPECIFIED,
            )

        signals = [
            competitor_pb2.CompetitiveSignal(
                topic=signal["topic"],
                observation=signal["observation"],
                source=competitor_pb2.Source(**signal["source"]),
            )
            for signal in result.competitive_signals
        ]
        return competitor_pb2.CompetitorAnalysisResponse(
            metadata=metadata,
            status=(
                competitor_pb2.RESPONSE_STATUS_DEGRADED
                if result.warnings
                else competitor_pb2.RESPONSE_STATUS_SUCCESS
            ),
            competitive_signals=signals,
            competitors=result.competitors,
            warnings=result.warnings,
            analysis=_analysis_message(result.analysis),
            evidence=[_evidence_message(source) for source in result.evidence],
        )

    async def _analyze(self, request, context, deadline_at: datetime | None):
        await self._settings.apply_delay()
        if self._settings.failure_mode is FailureMode.TRANSIENT_ERROR:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "injected transient failure")
        if self._settings.failure_mode is FailureMode.INVALID_RESPONSE:
            return None
        with request_span(request) as span:
            set_observation_input(
                span,
                {
                    "contract_version": request.metadata.contract_version,
                    "request_id": request.metadata.request_id,
                    "trace_id": request.metadata.trace_id,
                    "attempt": request.metadata.attempt,
                    "query": request.query,
                },
            )
            result = await self._runner.analyze(
                request.query,
                request.metadata.request_id,
                deadline_at=deadline_at,
            )
            set_observation_output(
                span,
                {
                    "analysis": result.analysis,
                    "evidence_count": len(result.evidence),
                    "warnings": result.warnings,
                },
            )
            return result


async def create_server(
    address: str = "[::]:50051",
    settings: DemoSettings | None = None,
    runner: CompetitorAnalystRunner | None = None,
) -> tuple[grpc.aio.Server, int]:
    server = grpc.aio.server()
    competitor_pb2_grpc.add_CompetitorAnalystServicer_to_server(
        CompetitorAnalystService(settings=settings, runner=runner),
        server,
    )

    health_service = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    await health_service.set("", health_pb2.HealthCheckResponse.SERVING)
    await health_service.set(
        competitor_pb2.DESCRIPTOR.services_by_name["CompetitorAnalyst"].full_name,
        health_pb2.HealthCheckResponse.SERVING,
    )

    port = server.add_insecure_port(address)
    return server, port


async def serve() -> None:
    server, _ = await create_server()
    await server.start()
    await server.wait_for_termination()


def _failure_response(metadata, code: int, message: str, *, retryable: bool):
    return competitor_pb2.CompetitorAnalysisResponse(
        metadata=metadata,
        status=competitor_pb2.RESPONSE_STATUS_FAILED,
        error=competitor_pb2.ContractError(code=code, message=message, retryable=retryable),
    )


def _deadline_from_unix_ms(value: int) -> datetime | None:
    if value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _claim_message(claim):
    return competitor_pb2.EvidenceClaim(text=claim.text, source_ids=claim.source_ids)


def _profile_message(profile):
    pricing = competitor_pb2.CompetitorPricing(
        model=profile.pricing.model,
        currency=profile.pricing.currency or "",
        source_ids=profile.pricing.source_ids,
    )
    if profile.pricing.annual_price is not None:
        pricing.annual_price = profile.pricing.annual_price
    return competitor_pb2.CompetitorProfile(
        id=profile.id,
        name=profile.name,
        type=profile.type,
        positioning=_claim_message(profile.positioning),
        target_segments=[_claim_message(value) for value in profile.target_segments],
        jobs_to_be_done=[_claim_message(value) for value in profile.jobs_to_be_done],
        platforms=[_claim_message(value) for value in profile.platforms],
        pricing=pricing,
        features=[_claim_message(value) for value in profile.features],
        traction_signals=[_claim_message(value) for value in profile.traction_signals],
        review_themes=[_claim_message(value) for value in profile.review_themes],
        distribution_channels=[_claim_message(value) for value in profile.distribution_channels],
        retention_mechanics=[_claim_message(value) for value in profile.retention_mechanics],
        strengths=[_claim_message(value) for value in profile.strengths],
        weaknesses=[_claim_message(value) for value in profile.weaknesses],
        confidence=profile.confidence,
        source_ids=profile.source_ids,
    )


def _analysis_message(analysis):
    return competitor_pb2.CompetitorAnalysis(
        competition_level=analysis.competition_level,
        market_structure=analysis.market_structure,
        tracked_products=analysis.tracked_products,
        feature_saturation=analysis.feature_saturation,
        switching_cost=analysis.switching_cost,
        competitors=[_profile_message(profile) for profile in analysis.competitors],
        gaps=[
            competitor_pb2.CompetitiveGap(
                id=gap.id,
                segment=gap.segment,
                unmet_need=gap.unmet_need,
                competitor_coverage=gap.competitor_coverage,
                demand_strength=gap.demand_strength,
                commercial_signal=gap.commercial_signal,
                confidence=gap.confidence,
                source_ids=gap.source_ids,
            )
            for gap in analysis.gaps
        ],
        coverage=analysis.coverage,
        source_ids=analysis.source_ids,
    )


def _evidence_message(source):
    return competitor_pb2.EvidenceSource(
        id=source.id,
        title=source.title,
        url=source.url,
        publisher=source.publisher,
        published_at_unix_ms=_datetime_to_unix_ms(source.published_at),
        retrieved_at_unix_ms=_datetime_to_unix_ms(source.retrieved_at),
        content=source.content,
    )


def _datetime_to_unix_ms(value: datetime | None) -> int:
    return 0 if value is None else int(value.timestamp() * 1000)


if __name__ == "__main__":
    asyncio.run(serve())
