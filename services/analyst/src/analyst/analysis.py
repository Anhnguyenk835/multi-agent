from distributed_agent_contracts import (
    AnalysisRequest,
    AnalysisResponse,
    Citation,
    ContractStatus,
    Source,
    copy_request_metadata,
    render_citation_links,
)

from analyst import llm_client
from analyst.llm_schema import LLMAnalysis
from analyst.prompts import SYSTEM_PROMPT, build_user_prompt
from analyst.settings import AnalystAISettings


def _citation(source: Source) -> Citation:
    return Citation(title=source.title, url=source.url, publisher=source.publisher)


async def analyze_live(request: AnalysisRequest, settings: AnalystAISettings) -> AnalysisResponse:
    user_prompt, sources = build_user_prompt(request)
    result = await llm_client.generate_structured(
        schema=LLMAnalysis,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        settings=settings,
    )
    citations = [_citation(source) for source in sources]
    content = render_citation_links(result.content, citations)
    return AnalysisResponse(
        **copy_request_metadata(request),
        status=ContractStatus.SUCCESS,
        content=content,
        citations=citations,
    )
