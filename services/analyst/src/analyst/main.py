from distributed_agent_contracts import (
    AnalysisRequest,
    AnalysisResponse,
    ContractError,
    ContractStatus,
    ErrorCode,
    copy_request_metadata,
)
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from analyst.analysis import analyze_fixture, analyze_live
from analyst.errors import InvalidOutputError, ProviderConfigurationError, ProviderUnavailableError
from analyst.settings import AIMode, DemoSettings, FailureMode


def create_app(settings: DemoSettings | None = None) -> FastAPI:
    runtime_settings = settings or DemoSettings.from_environment()
    app = FastAPI(title="Distributed Agents Analyst", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"service": "analyst", "status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"service": "analyst", "status": "ready"}

    @app.post("/analyze", response_model=AnalysisResponse)
    async def analyze(request: AnalysisRequest):
        try:
            await runtime_settings.apply_delay()
            if runtime_settings.failure_mode is FailureMode.TRANSIENT_ERROR:
                failure = AnalysisResponse(
                    **copy_request_metadata(request),
                    status=ContractStatus.FAILED,
                    error=ContractError(
                        code=ErrorCode.UPSTREAM_UNAVAILABLE,
                        message="injected transient Analyst failure",
                        retryable=True,
                    ),
                )
                return _respond(failure.model_dump(mode="json"), 503)
            if runtime_settings.failure_mode is FailureMode.INVALID_RESPONSE:
                return _respond({"status": "invalid"}, 200)

            return (
                analyze_fixture(request)
                if runtime_settings.ai.ai_mode is AIMode.FIXTURE
                else await analyze_live(request, runtime_settings.ai)
            )
        except ProviderConfigurationError:
            failure = _failure_response(
                request,
                ErrorCode.INTERNAL_ERROR,
                "Analyst provider configuration is invalid",
                retryable=False,
            )
            return _respond(failure.model_dump(mode="json"), 500)
        except ProviderUnavailableError:
            failure = _failure_response(
                request,
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Analyst LLM provider is unavailable",
                retryable=True,
            )
            return _respond(failure.model_dump(mode="json"), 503)
        except InvalidOutputError:
            failure = _failure_response(
                request,
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Analyst LLM returned invalid structured output",
                retryable=False,
            )
            return _respond(failure.model_dump(mode="json"), 502)

    return app


app = create_app()


def _failure_response(
    request: AnalysisRequest,
    code: ErrorCode,
    message: str,
    *,
    retryable: bool,
) -> AnalysisResponse:
    return AnalysisResponse(
        **copy_request_metadata(request),
        status=ContractStatus.FAILED,
        error=ContractError(code=code, message=message, retryable=retryable),
    )


def _respond(payload: dict[str, object], status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=payload)
