from distributed_agent_contracts import WriterRequest

SYSTEM_PROMPT = (
    "You are an executive brief writer. Use ONLY the analysis provided in "
    "the user message. Do not perform new research, do not search for "
    "information, and do not introduce any fact that is not present in the "
    "provided analysis. Write a complete, detailed executive brief in "
    "markdown: a title as a heading, then a thorough executive summary, key "
    "insights, and recommendations organized with headings and paragraphs "
    "or lists as appropriate — do not artificially shorten it. Cite every "
    "factual claim with [N], where N is the number of the source it came "
    "from in the numbered citations list below — never write a URL "
    "yourself and never invent a number that wasn't shown to you."
)


def build_user_prompt(request: WriterRequest) -> str:
    lines = [f"Query: {request.query}", "", "Analysis:", request.analysis, ""]

    if request.citations:
        lines.append("Citations:")
        lines.extend(
            f"[{index}] {citation.title} — {citation.publisher}"
            for index, citation in enumerate(request.citations, start=1)
        )
        lines.append("")

    if request.warnings:
        lines.append(f"Warnings: {', '.join(request.warnings)}")
        lines.append("")

    lines.append(
        "Write the executive brief now, grounded only in the analysis "
        "above, citing with [N] using the citation numbers above."
    )
    return "\n".join(lines)
