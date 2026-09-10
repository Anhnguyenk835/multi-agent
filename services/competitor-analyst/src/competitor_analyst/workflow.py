import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urldefrag

from distributed_agent_contracts import remaining_seconds
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import ValidationError

from competitor_analyst.agent import (
    SUBMIT_DISCOVERY_TOOL_NAME,
    SUBMIT_PROFILE_TOOL_NAME,
    SUBMIT_SYNTHESIS_TOOL_NAME,
    build_discovery_agent,
    build_profile_agent,
    build_synthesis_agent,
    collect_search_sources,
    extract_submitted_model,
)
from competitor_analyst.errors import InvalidOutputError
from competitor_analyst.models import (
    CompetitiveGap,
    CompetitorAnalysis,
    CompetitorDiscoveryInput,
    CompetitorProfile,
    CompetitorProfileInput,
    CompetitorSynthesisInput,
    DiscoveryCandidateInput,
    EvidenceClaim,
    EvidenceClaimInput,
    EvidenceSource,
)
from competitor_analyst.settings import DemoSettings
from competitor_analyst.telemetry import (
    operation_span,
    set_observation_input,
    set_observation_output,
)
from competitor_analyst.tools import ExaSourceResult


@dataclass(frozen=True)
class WorkflowResult:
    analysis: CompetitorAnalysis
    evidence: list[EvidenceSource]
    competitive_signals: list[dict[str, object]]
    warnings: list[str]


class EvidenceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, EvidenceSource] = {}

    def resolve_claim(
        self, claim: EvidenceClaimInput, sources_by_tag: dict[str, ExaSourceResult]
    ) -> EvidenceClaim:
        return EvidenceClaim(
            text=claim.text,
            source_ids=self.resolve_tags(claim.source_tags, sources_by_tag),
        )

    def resolve_tags(
        self, tags: list[str], sources_by_tag: dict[str, ExaSourceResult]
    ) -> list[str]:
        source_ids: list[str] = []
        for tag in dict.fromkeys(tags):
            source = sources_by_tag.get(tag)
            if source is None:
                raise InvalidOutputError(
                    f"competitor profile referenced unknown source tag {tag!r}"
                )
            source_id = self._register(source)
            if source_id not in source_ids:
                source_ids.append(source_id)
        return source_ids

    def get(self, source_id: str) -> EvidenceSource:
        return self._sources[source_id]

    def values(self) -> list[EvidenceSource]:
        return list(self._sources.values())

    def _register(self, source: ExaSourceResult) -> str:
        normalized_url = urldefrag(source.url.strip().rstrip("/"))[0]
        source_id = f"src_{hashlib.sha256(normalized_url.encode()).hexdigest()[:16]}"
        self._sources.setdefault(
            source_id,
            EvidenceSource(
                id=source_id,
                title=source.title,
                url=source.url,
                publisher=source.publisher,
                published_at=source.published_at,
                retrieved_at=source.retrieved_at,
                content=source.content,
            ),
        )
        return source_id


class CompetitorAnalysisWorkflow:
    def __init__(self, settings: DemoSettings) -> None:
        self._settings = settings

    async def run(
        self,
        query: str,
        request_id: str,
        *,
        deadline_at: datetime | None,
    ) -> WorkflowResult:
        query = query.strip()
        if not query:
            raise InvalidOutputError("competitor analysis query is empty")

        with operation_span(
            "competitor_analysis.workflow",
            observation_type="agent",
            attributes={"app.workflow.kind": "competitor_analysis"},
        ) as workflow_span:
            set_observation_input(workflow_span, {"app_market": query})
            grounded_candidates = await self._discover(query, request_id, deadline_at)
            selected = select_competitors(
                grounded_candidates,
                limit=self._settings.workflow.max_competitors,
            )
            if not selected:
                raise InvalidOutputError("competitor discovery returned no grounded candidates")

            registry = EvidenceRegistry()
            profiles, failed = await self._profile_many(
                query, selected, request_id, deadline_at, registry
            )

            for round_number in range(self._settings.workflow.max_gap_fill_rounds):
                repair = [
                    candidate
                    for candidate in selected
                    if candidate.name in failed
                    or profile_quality_issues(_profile_by_name(profiles, candidate.name))
                ]
                if not repair:
                    break
                repaired, still_failed = await self._profile_many(
                    query,
                    repair,
                    f"{request_id}-gap-{round_number + 1}",
                    deadline_at,
                    registry,
                    gap_fill=True,
                )
                profiles = _replace_profiles(profiles, repaired)
                repaired_names = {_canonical_name(profile.name) for profile in repaired}
                failed = {
                    name for name in failed if _canonical_name(name) not in repaired_names
                } | still_failed

            if not profiles:
                raise InvalidOutputError("competitor profiling produced no valid profiles")

            synthesis = await self._synthesize(query, profiles, request_id, deadline_at)
            analysis = build_analysis(
                profiles,
                synthesis,
                registry,
                selected_count=len(selected),
            )
            warnings = quality_warnings(analysis, failed)
            result = WorkflowResult(
                analysis=analysis,
                evidence=registry.values(),
                competitive_signals=legacy_signals(analysis, registry),
                warnings=warnings,
            )
            set_observation_output(
                workflow_span,
                {
                    "analysis": analysis,
                    "evidence_count": len(result.evidence),
                    "warnings": warnings,
                },
            )
            return result

    async def _discover(
        self, query: str, request_id: str, deadline_at: datetime | None
    ) -> list[DiscoveryCandidateInput]:
        phase_deadline = _phase_deadline(
            deadline_at, self._settings.workflow.discovery_timeout_seconds, "discovery"
        )
        with operation_span(
            "competitor_analysis.discover",
            observation_type="agent",
            attributes={"app.workflow.phase": "discovery"},
        ) as span:
            set_observation_input(span, {"app_market": query})
            agent = build_discovery_agent(
                self._settings.ai,
                self._settings.search,
                deadline_at=phase_deadline,
                max_search_calls=self._settings.workflow.discovery_search_calls,
            )
            events = await _run_agent_until(agent, query, f"{request_id}-discovery", phase_deadline)
            discovery = extract_submitted_model(
                events,
                tool_name=SUBMIT_DISCOVERY_TOOL_NAME,
                model_type=CompetitorDiscoveryInput,
            )
            if discovery is None:
                raise InvalidOutputError("competitor discovery completed without structured output")
            sources = collect_search_sources(events)
            grounded = [item for item in discovery.candidates if item.source_tag in sources]
            if not grounded:
                raise InvalidOutputError("competitor discovery returned no grounded candidates")
            set_observation_output(
                span,
                {"candidates": [candidate.model_dump(mode="json") for candidate in grounded]},
            )
            return grounded

    async def _profile_many(
        self,
        query: str,
        candidates: list[DiscoveryCandidateInput],
        request_id: str,
        deadline_at: datetime | None,
        registry: EvidenceRegistry,
        *,
        gap_fill: bool = False,
    ) -> tuple[list[CompetitorProfile], set[str]]:
        semaphore = asyncio.Semaphore(self._settings.workflow.profile_concurrency)

        async def run_one(candidate: DiscoveryCandidateInput) -> CompetitorProfile | None:
            async with semaphore:
                try:
                    return await self._profile(
                        query, candidate, request_id, deadline_at, registry, gap_fill=gap_fill
                    )
                except (InvalidOutputError, ValidationError):
                    return None

        results = await asyncio.gather(*(run_one(candidate) for candidate in candidates))
        profiles = [profile for profile in results if profile is not None]
        failed = {
            candidate.name
            for candidate, profile in zip(candidates, results, strict=True)
            if profile is None
        }
        return profiles, failed

    async def _profile(
        self,
        query: str,
        candidate: DiscoveryCandidateInput,
        request_id: str,
        deadline_at: datetime | None,
        registry: EvidenceRegistry,
        *,
        gap_fill: bool,
    ) -> CompetitorProfile:
        phase_deadline = _phase_deadline(
            deadline_at, self._settings.workflow.profile_timeout_seconds, "profiling"
        )
        with operation_span(
            "competitor_analysis.profile",
            observation_type="agent",
            attributes={
                "app.workflow.phase": "gap_fill" if gap_fill else "profile",
                "app.competitor.name": candidate.name,
                "app.competitor.type": candidate.type,
            },
        ) as span:
            set_observation_input(
                span,
                {
                    "app_market": query,
                    "competitor": candidate.model_dump(mode="json"),
                    "gap_fill": gap_fill,
                },
            )
            agent = build_profile_agent(
                self._settings.ai,
                self._settings.search,
                deadline_at=phase_deadline,
                max_search_calls=self._settings.workflow.profile_search_calls,
            )
            instruction = (
                f"App market: {query}\nCompetitor: {candidate.name}\n"
                f"Competitor type: {candidate.type}\nDiscovery rationale: {candidate.rationale}"
            )
            if gap_fill:
                instruction += "\nThis is a gap-fill pass. Prioritize missing core evidence."
            events = await _run_agent_until(
                agent,
                instruction,
                f"{request_id}-profile-{_slug(candidate.name)}",
                phase_deadline,
            )
            structured = extract_submitted_model(
                events,
                tool_name=SUBMIT_PROFILE_TOOL_NAME,
                model_type=CompetitorProfileInput,
            )
            if structured is None:
                raise InvalidOutputError(f"profile for {candidate.name} has no structured output")
            if _canonical_name(structured.name) != _canonical_name(candidate.name):
                raise InvalidOutputError(
                    f"profile returned {structured.name!r} instead of {candidate.name!r}"
                )
            profile = ground_profile(structured, collect_search_sources(events), registry)
            set_observation_output(span, profile)
            return profile

    async def _synthesize(
        self,
        query: str,
        profiles: list[CompetitorProfile],
        request_id: str,
        deadline_at: datetime | None,
    ) -> CompetitorSynthesisInput:
        phase_deadline = _phase_deadline(
            deadline_at, self._settings.workflow.synthesis_timeout_seconds, "synthesis"
        )
        with operation_span(
            "competitor_analysis.synthesize",
            observation_type="agent",
            attributes={
                "app.workflow.phase": "synthesis",
                "app.competitor.count": len(profiles),
            },
        ) as span:
            set_observation_input(
                span,
                {"app_market": query, "competitors": [profile.name for profile in profiles]},
            )
            agent = build_synthesis_agent(self._settings.ai, deadline_at=phase_deadline)
            payload = {
                "app_market": query,
                "profiles": [profile.model_dump(mode="json") for profile in profiles],
            }
            events = await _run_agent_until(
                agent,
                json.dumps(payload, separators=(",", ":")),
                f"{request_id}-synthesis",
                phase_deadline,
            )
            synthesis = extract_submitted_model(
                events,
                tool_name=SUBMIT_SYNTHESIS_TOOL_NAME,
                model_type=CompetitorSynthesisInput,
            )
            if synthesis is None:
                raise InvalidOutputError("competitor synthesis completed without structured output")
            set_observation_output(span, synthesis)
            return synthesis


async def _run_agent(agent, message: str, session_id: str) -> list[Event]:
    runner = Runner(
        agent=agent,
        app_name="competitor-analyst",
        session_service=InMemorySessionService(),
        auto_create_session=True,
    )
    events: list[Event] = []
    async for event in runner.run_async(
        user_id="orchestrator",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        events.append(event)
    return events


async def _run_agent_until(
    agent, message: str, session_id: str, deadline_at: datetime
) -> list[Event]:
    timeout = remaining_seconds(deadline_at)
    if timeout <= 0:
        raise TimeoutError("competitor analyst phase deadline exceeded")
    async with asyncio.timeout(timeout):
        return await _run_agent(agent, message, session_id)


def select_competitors(
    candidates: list[DiscoveryCandidateInput], *, limit: int
) -> list[DiscoveryCandidateInput]:
    unique: dict[str, DiscoveryCandidateInput] = {}
    for candidate in candidates:
        unique.setdefault(_canonical_name(candidate.name), candidate)
    ordered = list(unique.values())
    direct = [item for item in ordered if item.type == "direct"]
    others = [item for item in ordered if item.type != "direct"]
    return (direct + others)[:limit]


def ground_profile(
    profile: CompetitorProfileInput,
    sources_by_tag: dict[str, ExaSourceResult],
    registry: EvidenceRegistry,
) -> CompetitorProfile:
    def claims(items: list[EvidenceClaimInput]) -> list[EvidenceClaim]:
        return [registry.resolve_claim(item, sources_by_tag) for item in items]

    pricing_source_ids = registry.resolve_tags(profile.pricing.source_tags, sources_by_tag)
    grounded = CompetitorProfile(
        id=f"competitor_{hashlib.sha256(_canonical_name(profile.name).encode()).hexdigest()[:12]}",
        name=profile.name,
        type=profile.type,
        positioning=registry.resolve_claim(profile.positioning, sources_by_tag),
        target_segments=claims(profile.target_segments),
        jobs_to_be_done=claims(profile.jobs_to_be_done),
        platforms=claims(profile.platforms),
        pricing={
            "model": profile.pricing.model,
            "annual_price": profile.pricing.annual_price,
            "currency": profile.pricing.currency,
            "source_ids": pricing_source_ids,
        },
        features=claims(profile.features),
        traction_signals=claims(profile.traction_signals),
        review_themes=claims(profile.review_themes),
        distribution_channels=claims(profile.distribution_channels),
        retention_mechanics=claims(profile.retention_mechanics),
        strengths=claims(profile.strengths),
        weaknesses=claims(profile.weaknesses),
        confidence=0,
        source_ids=[],
    )
    source_ids = _profile_source_ids(grounded)
    coverage_fields = [
        grounded.target_segments,
        grounded.jobs_to_be_done,
        grounded.platforms,
        grounded.features,
        grounded.traction_signals,
        grounded.review_themes,
        grounded.distribution_channels,
        grounded.retention_mechanics,
        grounded.strengths,
        grounded.weaknesses,
    ]
    confidence = min(95, 35 + sum(bool(value) for value in coverage_fields) * 5 + len(source_ids))
    return grounded.model_copy(update={"confidence": confidence, "source_ids": source_ids})


def build_analysis(
    profiles: list[CompetitorProfile],
    synthesis: CompetitorSynthesisInput,
    registry: EvidenceRegistry,
    *,
    selected_count: int,
) -> CompetitorAnalysis:
    known_sources = {source.id for source in registry.values()}
    gaps: list[CompetitiveGap] = []
    for index, gap in enumerate(synthesis.gaps):
        source_ids = list(dict.fromkeys(gap.source_ids))
        unknown = set(source_ids) - known_sources
        if unknown:
            raise InvalidOutputError(f"synthesis referenced unknown source IDs: {sorted(unknown)}")
        confidence = min(90, 50 + len(source_ids) * 5)
        gaps.append(
            CompetitiveGap(
                id=f"gap_{index + 1}",
                segment=gap.segment,
                unmet_need=gap.unmet_need,
                competitor_coverage=gap.competitor_coverage,
                demand_strength=gap.demand_strength,
                commercial_signal=gap.commercial_signal,
                confidence=confidence,
                source_ids=source_ids,
            )
        )
    source_ids = list(
        dict.fromkeys(source for profile in profiles for source in profile.source_ids)
    )
    return CompetitorAnalysis(
        competition_level=synthesis.competition_level,
        market_structure=synthesis.market_structure,
        tracked_products=len(profiles),
        feature_saturation=synthesis.feature_saturation,
        switching_cost=synthesis.switching_cost,
        competitors=profiles,
        gaps=gaps,
        coverage=round(len(profiles) / selected_count * 100),
        source_ids=source_ids,
    )


def profile_quality_issues(profile: CompetitorProfile | None) -> list[str]:
    if profile is None:
        return ["missing profile"]
    issues = []
    for field_name in ("features", "strengths", "weaknesses"):
        if not getattr(profile, field_name):
            issues.append(f"missing {field_name}")
    if profile.pricing.annual_price is not None and not profile.pricing.source_ids:
        issues.append("ungrounded annual price")
    return issues


def quality_warnings(analysis: CompetitorAnalysis, failed: set[str]) -> list[str]:
    warnings = [f"No valid profile was produced for {name}" for name in sorted(failed)]
    for profile in analysis.competitors:
        warnings.extend(f"{profile.name}: {issue}" for issue in profile_quality_issues(profile))
    if analysis.coverage < 100:
        warnings.append(f"Competitor profile coverage is {analysis.coverage}%")
    return warnings


def legacy_signals(
    analysis: CompetitorAnalysis, registry: EvidenceRegistry
) -> list[dict[str, object]]:
    signals: list[dict[str, object]] = []
    for profile in analysis.competitors:
        claims = [("Positioning", profile.positioning)]
        claims += [("Strength", item) for item in profile.strengths[:1]]
        claims += [("Weakness", item) for item in profile.weaknesses[:1]]
        for topic, claim in claims:
            if not claim.source_ids:
                continue
            source = registry.get(claim.source_ids[0])
            signals.append(
                {
                    "topic": f"{profile.name}: {topic}",
                    "observation": claim.text,
                    "source": {
                        "title": source.title,
                        "url": source.url,
                        "publisher": source.publisher,
                        "published_at_unix_ms": _unix_ms(source.published_at),
                        "retrieved_at_unix_ms": _unix_ms(source.retrieved_at),
                        "content": source.content,
                    },
                }
            )
    return signals[:20]


def _profile_source_ids(profile: CompetitorProfile) -> list[str]:
    ids = list(profile.positioning.source_ids) + list(profile.pricing.source_ids)
    for field_name in (
        "target_segments",
        "jobs_to_be_done",
        "features",
        "traction_signals",
        "review_themes",
        "distribution_channels",
        "retention_mechanics",
        "strengths",
        "weaknesses",
    ):
        ids.extend(source for claim in getattr(profile, field_name) for source in claim.source_ids)
    return list(dict.fromkeys(ids))


def _replace_profiles(
    profiles: list[CompetitorProfile], repaired: list[CompetitorProfile]
) -> list[CompetitorProfile]:
    replacements = {_canonical_name(profile.name): profile for profile in repaired}
    result = []
    for profile in profiles:
        candidate = replacements.pop(_canonical_name(profile.name), None)
        if candidate is None:
            result.append(profile)
            continue
        current_score = (-len(profile_quality_issues(profile)), profile.confidence)
        candidate_score = (-len(profile_quality_issues(candidate)), candidate.confidence)
        result.append(candidate if candidate_score > current_score else profile)
    result.extend(replacements.values())
    return result


def _profile_by_name(profiles: list[CompetitorProfile], name: str) -> CompetitorProfile | None:
    canonical = _canonical_name(name)
    return next((item for item in profiles if _canonical_name(item.name) == canonical), None)


def _canonical_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")[:48]


def _phase_deadline(
    workflow_deadline: datetime | None, phase_seconds: float, phase: str
) -> datetime:
    now = datetime.now(UTC)
    phase_deadline = now + timedelta(seconds=phase_seconds)
    if workflow_deadline is not None:
        normalized = (
            workflow_deadline.replace(tzinfo=UTC)
            if workflow_deadline.tzinfo is None
            else workflow_deadline
        )
        phase_deadline = min(phase_deadline, normalized)
    if remaining_seconds(phase_deadline) <= 2:
        raise TimeoutError(f"competitor analyst deadline reached before {phase}")
    return phase_deadline


def _unix_ms(value: datetime | None) -> int:
    return 0 if value is None else int(value.timestamp() * 1000)
