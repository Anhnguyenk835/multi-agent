from dataclasses import dataclass
from datetime import datetime

import openai
from pydantic import ValidationError

from competitor_analyst.errors import (
    InvalidOutputError,
    ProviderConfigurationError,
    ProviderUnavailableError,
)
from competitor_analyst.models import CompetitorAnalysis, EvidenceSource
from competitor_analyst.settings import DemoSettings
from competitor_analyst.workflow import CompetitorAnalysisWorkflow

_NO_RETRY = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.BadRequestError,
)


@dataclass(frozen=True)
class CompetitorAnalysisResult:
    competitive_signals: list[dict[str, object]]
    competitors: list[str]
    analysis: CompetitorAnalysis
    evidence: list[EvidenceSource]
    warnings: list[str]


class CompetitorAnalystRunner:
    def __init__(
        self,
        settings: DemoSettings | None = None,
        workflow: CompetitorAnalysisWorkflow | None = None,
    ) -> None:
        self._settings = settings or DemoSettings.from_environment()
        self._workflow = workflow or CompetitorAnalysisWorkflow(self._settings)

    async def analyze(
        self,
        query: str,
        request_id: str,
        *,
        deadline_at: datetime | None = None,
    ) -> CompetitorAnalysisResult:
        try:
            result = await self._workflow.run(
                query,
                request_id,
                deadline_at=deadline_at,
            )
        except TimeoutError:
            raise
        except _NO_RETRY as error:
            raise ProviderConfigurationError(
                "LLM gateway rejected the competitor analyst request"
            ) from error
        except InvalidOutputError:
            raise
        except ValidationError as error:
            raise InvalidOutputError(
                "competitor analyst returned invalid structured output"
            ) from error
        except Exception as error:
            raise ProviderUnavailableError("competitor analyst upstream is unavailable") from error

        return CompetitorAnalysisResult(
            competitive_signals=result.competitive_signals,
            competitors=[profile.name for profile in result.analysis.competitors],
            analysis=result.analysis,
            evidence=result.evidence,
            warnings=result.warnings,
        )
