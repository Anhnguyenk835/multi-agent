import asyncio
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv

from analyst.errors import ProviderConfigurationError

# Own .env per service, not a shared root file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
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


class AIMode(StrEnum):
    FIXTURE = "fixture"
    LIVE = "live"


class FailureMode(StrEnum):
    NONE = "none"
    TIMEOUT = "timeout"
    TRANSIENT_ERROR = "transient_error"
    INVALID_RESPONSE = "invalid_response"


@dataclass(frozen=True, slots=True)
class AnalystAISettings:
    ai_mode: AIMode = AIMode.FIXTURE
    openai_api_key: str | None = None
    openai_model: str = _DEFAULT_OPENAI_MODEL
    llm_timeout_seconds: float = 30.0

    @classmethod
    def from_environment(cls) -> "AnalystAISettings":
        ai_mode = AIMode(os.getenv("AI_MODE", AIMode.FIXTURE.value))
        openai_api_key = os.getenv("OPENAI_API_KEY") or None

        if ai_mode is AIMode.LIVE and not openai_api_key:
            raise ProviderConfigurationError("AI_MODE=live requires OPENAI_API_KEY to be set")

        return cls(
            ai_mode=ai_mode,
            openai_api_key=openai_api_key,
            openai_model=_model_id_from_environment("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL),
            llm_timeout_seconds=max(1.0, float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))),
        )


@dataclass(frozen=True, slots=True)
class DemoSettings:
    failure_mode: FailureMode = FailureMode.NONE
    delay_seconds: float = 0.25
    ai: AnalystAISettings = field(default_factory=AnalystAISettings)

    @classmethod
    def from_environment(cls) -> "DemoSettings":
        failure_mode = FailureMode(os.getenv("DEMO_FAILURE_MODE", FailureMode.NONE))
        delay_ms = max(0, int(os.getenv("DEMO_FAILURE_DELAY_MS", "250")))
        return cls(
            failure_mode=failure_mode,
            delay_seconds=delay_ms / 1_000,
            ai=AnalystAISettings.from_environment(),
        )

    async def apply_delay(self) -> None:
        if self.failure_mode is FailureMode.TIMEOUT:
            await asyncio.sleep(self.delay_seconds)


def _model_id_from_environment(name: str, default: str) -> str:
    return (os.getenv(name) or default).strip().translate(_MODEL_ID_TRANSLATION).lower()
