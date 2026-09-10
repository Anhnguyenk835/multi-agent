from langchain_openai import ChatOpenAI

from market_analyst.errors import ProviderConfigurationError
from market_analyst.settings import MarketAnalystAISettings


def build_chat_model(
    settings: MarketAnalystAISettings,
    *,
    timeout_seconds: float | None = None,
    gateway_timeout_seconds: float | None = None,
) -> ChatOpenAI:
    if not settings.gateway_api_key:
        raise ProviderConfigurationError("LLM_GATEWAY_API_KEY is required")

    timeout = timeout_seconds or settings.llm_timeout_seconds
    return ChatOpenAI(
        model=settings.model_route,
        api_key=settings.gateway_api_key,
        base_url=settings.gateway_base_url,
        timeout=timeout,
        max_completion_tokens=settings.llm_max_output_tokens,
        max_retries=0,
        extra_body=(
            {"request_timeout": gateway_timeout_seconds}
            if gateway_timeout_seconds is not None
            else None
        ),
    )


def model_timeouts(
    settings: MarketAnalystAISettings,
    remaining: float,
) -> tuple[float, float]:
    provider_budget = (remaining - 2.0) / settings.gateway_max_provider_attempts
    return min(settings.llm_timeout_seconds, provider_budget), remaining - 1.0
