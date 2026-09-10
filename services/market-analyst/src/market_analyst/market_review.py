from distributed_agent_contracts import (
    ConversationReviewContext,
    EvidenceFact,
    MarketAnalysisResponse,
)

_SECTION_DIMENSIONS = {
    "verdict": set(),
    "scorecard": set(),
    "market_size": {"market_size"},
    "momentum": {"momentum"},
    "customer_segments": {"customers"},
    "commercial_dynamics": {"commercial"},
    "market_accessibility": {"accessibility"},
    "risks": {"risks_opportunities"},
    "opportunity_gaps": {"risks_opportunities"},
    "competitors": {"competitors"},
}


def dimensions_for_sections(section_ids: list[str]) -> set[str]:
    dimensions: set[str] = set()
    for section_id in section_ids:
        dimensions.update(_SECTION_DIMENSIONS.get(section_id, ()))
    return dimensions


def build_review_context(
    *,
    report: MarketAnalysisResponse,
    facts: list[EvidenceFact],
    conversation: ConversationReviewContext,
    section_ids: list[str],
    max_facts: int = 80,
    max_messages: int = 12,
) -> dict[str, object]:
    dimensions = dimensions_for_sections(section_ids)
    selected_facts = [fact for fact in facts if not dimensions or fact.dimension in dimensions][
        :max_facts
    ]
    return {
        "market": report.market.model_dump(mode="json"),
        "selected_sections": _select_sections(report, section_ids),
        "review_summary": conversation.summary,
        "recent_messages": [
            message.model_dump(mode="json")
            for message in conversation.recent_messages[-max_messages:]
        ],
        "selected_facts": [fact.model_dump(mode="json") for fact in selected_facts],
    }


def _select_sections(
    report: MarketAnalysisResponse,
    section_ids: list[str],
) -> dict[str, object]:
    overview = report.overview.model_dump(mode="json")
    if not section_ids:
        return {
            "verdict": overview["verdict"],
            "scorecard": overview["scorecard"],
            "competitor_summary": report.competitors.summary.model_dump(mode="json"),
        }
    selected = {
        section_id: overview[section_id] for section_id in section_ids if section_id in overview
    }
    if "competitors" in section_ids:
        selected["competitors"] = report.competitors.model_dump(mode="json")
    return selected
