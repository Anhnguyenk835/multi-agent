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
from analyst.prompts import SYSTEM_PROMPT, _collect_sources, build_user_prompt
from analyst.settings import AnalystAISettings


def _citation(source: Source) -> Citation:
    return Citation(title=source.title, url=source.url, publisher=source.publisher)


def analyze_fixture(request: AnalysisRequest) -> AnalysisResponse:
    items = _collect_sources(request)
    citations = [_citation(item.source) for item in items]

    lines = [f"# Analysis: {request.query}", ""]

    themes: list[str] = []
    if request.research_findings:
        themes.append("Developer adoption and integration")
    if request.market_signals:
        themes.append("Enterprise governance and market fit")
    if themes:
        lines.append("## Themes")
        lines.extend(f"- {theme}" for theme in themes)
        lines.append("")

    lines.append("## Key Insights")
    for index, item in enumerate(items, start=1):
        lines.append(f"- {item.detail} [{index}]")
    if request.competitors:
        lines.append(f"- Competitive set: {', '.join(request.competitors[:5])}.")
    lines.append("")

    lines.append("## Risks")
    lines.append(
        "- Fixture evidence is illustrative and must not be treated as live market data."
    )
    lines.append("- Production decisions require source verification and current pricing data.")

    content = render_citation_links("\n".join(lines), citations)
    return AnalysisResponse(
        **copy_request_metadata(request),
        status=ContractStatus.SUCCESS,
        content=content,
        citations=citations,
    )


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
