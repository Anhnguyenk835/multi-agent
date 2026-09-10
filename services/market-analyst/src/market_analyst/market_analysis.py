import math
from collections.abc import Iterable

from distributed_agent_contracts.market_analysis import (
    CommercialDynamics,
    MarketAnalysisResponse,
    MarketScorecard,
    MarketSize,
    MetricChange,
)

_LEVEL_SCORE = {"low": 35, "moderate": 60, "high": 80, "unknown": 35}


def calculate_scorecard(report: MarketAnalysisResponse) -> MarketScorecard:
    overview = report.overview
    momentum_base = {
        "growing": 80,
        "stable": 55,
        "declining": 25,
        "uncertain": 40,
    }[overview.momentum.direction]
    demand_confidence = _average(segment.confidence for segment in overview.customer_segments)
    metric_confidence = _average(metric.confidence for metric in overview.market_size.metrics)

    return MarketScorecard(
        demand=_clamp((demand_confidence + momentum_base) / 2),
        market_size=_clamp(metric_confidence),
        momentum=_clamp(momentum_base),
        commercial_quality=_commercial_score(overview.commercial_dynamics),
        accessibility=_clamp(_LEVEL_SCORE[overview.market_accessibility.level]),
        competitive_headroom=_competitive_headroom(report),
    )


def normalize_revenue_history(market_size: MarketSize) -> MarketSize:
    points = sorted(market_size.revenue_history, key=lambda point: point.period)
    metrics = list(market_size.metrics)
    if len(points) >= 2:
        previous, current = points[-2:]
        if previous.value > 0:
            growth = (current.value - previous.value) / previous.value * 100
            for index, metric in enumerate(metrics):
                if metric.unit == "USD" and metric.change is None:
                    metrics[index] = metric.model_copy(
                        update={
                            "change": MetricChange(
                                value=round(growth, 2),
                                unit="percent",
                                period="YoY",
                            )
                        }
                    )
                    break
    return market_size.model_copy(update={"metrics": metrics, "revenue_history": points})


def validate_source_lineage(report: MarketAnalysisResponse) -> None:
    known = {source.id for source in report.evidence}
    referenced = set(_walk_source_ids(report.model_dump(mode="json")))
    unknown = referenced - known
    if unknown:
        raise ValueError(f"report references unknown source IDs: {sorted(unknown)}")


def _walk_source_ids(value: object) -> Iterable[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "source_ids" and isinstance(nested, list):
                yield from (item for item in nested if isinstance(item, str))
            else:
                yield from _walk_source_ids(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_source_ids(nested)


def _commercial_score(commercial: CommercialDynamics) -> int:
    willingness = _LEVEL_SCORE[commercial.willingness_to_pay]
    retention_penalty = {"low": 0, "moderate": 10, "high": 20, "unknown": 15}[
        commercial.retention_pressure
    ]
    return _clamp(willingness - retention_penalty)


def _competitive_headroom(report: MarketAnalysisResponse) -> int:
    summary = report.competitors.summary
    competition = _LEVEL_SCORE[summary.competition_level]
    saturation = _LEVEL_SCORE[summary.feature_saturation]
    return _clamp(100 - (competition + saturation) / 2)


def _average(values: Iterable[int]) -> int:
    items = list(values)
    return round(sum(items) / len(items)) if items else 30


def _clamp(value: float) -> int:
    if not math.isfinite(value):
        return 0
    return max(0, min(100, round(value)))
