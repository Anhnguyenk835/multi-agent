import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Own .env per service, not a shared root file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_DEFAULT_MODEL_ROUTE = "research-fast"
_DEFAULT_GATEWAY_BASE_URL = "http://llm-gateway:4000/v1"
_MODEL_ID_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


@dataclass(frozen=True, slots=True)
class ResearcherAISettings:
    gateway_api_key: str | None = None
    gateway_base_url: str = _DEFAULT_GATEWAY_BASE_URL
    model_route: str = _DEFAULT_MODEL_ROUTE
    llm_timeout_seconds: float = 60.0
    llm_max_output_tokens: int = 2_000

    @classmethod
    def from_environment(cls) -> "ResearcherAISettings":
        gateway_api_key = os.getenv("LLM_GATEWAY_API_KEY") or None
        gateway_base_url = os.getenv("LLM_GATEWAY_BASE_URL") or _DEFAULT_GATEWAY_BASE_URL

        return cls(
            gateway_api_key=gateway_api_key,
            gateway_base_url=gateway_base_url.rstrip("/"),
            model_route=_model_id_from_environment("LLM_MODEL_ROUTE", _DEFAULT_MODEL_ROUTE),
            llm_timeout_seconds=max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))),
            llm_max_output_tokens=max(1, int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "2000"))),
        )


@dataclass(frozen=True, slots=True)
class ResearcherExaSettings:
    exa_api_key: str | None = None
    exa_max_results: int = 4
    # Caps context window/rate-limit exposure across repeated search calls.
    exa_content_max_characters: int = 4_000

    @classmethod
    def from_environment(cls) -> "ResearcherExaSettings":
        return cls(
            exa_api_key=os.getenv("EXA_API_KEY") or None,
            exa_max_results=max(1, int(os.getenv("EXA_MAX_RESULTS", "4"))),
            exa_content_max_characters=max(
                500, int(os.getenv("EXA_CONTENT_MAX_CHARACTERS", "4000"))
            ),
        )


@dataclass(frozen=True, slots=True)
class DemoSettings:
    ai: ResearcherAISettings = field(default_factory=ResearcherAISettings)
    exa: ResearcherExaSettings = field(default_factory=ResearcherExaSettings)

    @classmethod
    def from_environment(cls) -> "DemoSettings":
        return cls(
            ai=ResearcherAISettings.from_environment(),
            exa=ResearcherExaSettings.from_environment(),
        )


def _model_id_from_environment(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().translate(_MODEL_ID_TRANSLATION).lower()
