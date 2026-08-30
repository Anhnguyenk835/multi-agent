from dataclasses import dataclass

from distributed_agent_contracts import AnalysisRequest, Source

SYSTEM_PROMPT = (
    "You are a research analyst writing a detailed analysis from Researcher's "
    "findings and Market Agent's signals. Use ONLY the numbered sources "
    "provided in the user message — each includes the full text of its "
    "source page, not just a one-line summary; read it and synthesize from "
    "it in depth. Do not perform new research and do not invent facts that "
    "are not present in the provided material. Write in markdown: use "
    "headings to organize themes, key insights, and risks, and multiple "
    "paragraphs where the material supports it — do not artificially "
    "shorten your analysis. Cite every factual claim with [N], where N is "
    "the number of the source it came from — never write a URL yourself "
    "and never invent a number that wasn't shown to you."
)


@dataclass(frozen=True)
class _Sourced:
    origin: str
    label: str
    detail: str
    source: Source


def _collect_sources(request: AnalysisRequest) -> list[_Sourced]:
    items = [
        _Sourced("Researcher", finding.title, finding.claim, finding.source)
        for finding in request.research_findings
    ]
    items.extend(
        _Sourced("Market Agent", signal.topic, signal.observation, signal.source)
        for signal in request.market_signals
    )
    return items


def build_user_prompt(request: AnalysisRequest) -> tuple[str, list[Source]]:
    """Build the prompt and the numbered source list its `[N]` markers refer to."""
    items = _collect_sources(request)
    lines = [f"Query: {request.query}", "", "Sources:"]
    for index, item in enumerate(items, start=1):
        lines.append(f"[{index}] {item.label} — from {item.origin}")
        lines.append(f"    Claim/observation: {item.detail}")
        lines.append(f"    Publisher: {item.source.publisher}")
        if item.source.content:
            lines.append(f"    Content: {item.source.content}")
        lines.append("")

    if request.competitors:
        lines.append(f"Competitors: {', '.join(request.competitors)}")
        lines.append("")

    lines.append(
        "Write a detailed, thorough markdown analysis of themes, key "
        "insights, and risks for the query above, grounded only in the "
        "numbered sources. Be as complete as the material supports — do "
        "not limit yourself to a fixed number of bullet points. Cite with "
        "[N] using the source numbers above."
    )
    return "\n".join(lines), [item.source for item in items]
