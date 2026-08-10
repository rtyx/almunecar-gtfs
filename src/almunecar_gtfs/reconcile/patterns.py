"""Reconcile observations into canonical route patterns.

Patterns, not routes, are what actually gets operated: 2A outbound, 2B inbound
and the 3B Cabria extension are three different ordered stop sequences. A
pattern whose intermediate offsets are unknown is marked ``not_publishable``
instead of being padded with invented times.
"""

from __future__ import annotations

from almunecar_gtfs.models import (
    Pattern,
    PatternStop,
    PublicationStatus,
    Season,
    TimingMethod,
    TimingModel,
)
from almunecar_gtfs.provenance import EvidenceStore, Observation, SourceType
from almunecar_gtfs.reconcile.fields import Resolver


def _timing_methods(
    raw: list[str], stop_count: int, entity: str, problems: list[str]
) -> list[TimingMethod]:
    if not raw:
        return [TimingMethod.UNKNOWN] * stop_count
    if len(raw) != stop_count:
        problems.append(
            f"{entity}: timing_methods has {len(raw)} entries but the sequence has {stop_count}"
        )
        return [TimingMethod.UNKNOWN] * stop_count
    methods = []
    for token in raw:
        try:
            methods.append(TimingMethod(token))
        except ValueError:
            problems.append(f"{entity}: unknown timing method {token!r}")
            methods.append(TimingMethod.UNKNOWN)
    return methods


def reconcile_patterns(evidence: EvidenceStore) -> tuple[list[Pattern], list[str]]:
    resolver = Resolver(evidence)
    patterns: list[Pattern] = []

    for entity in evidence.entities("pattern"):
        pattern_id = entity.split(":", 1)[1]
        route_id = resolver.require(entity, "route_id")
        sequence = resolver.require(entity, "stop_sequence")
        headsign = resolver.require(entity, "headsign")
        if route_id is None or sequence is None or headsign is None:
            continue

        stop_ids: list[str] = sequence.value
        if len(stop_ids) < 2:
            resolver.problems.append(f"{entity}: stop sequence has fewer than two stops")
            continue

        season_text = resolver.value(entity, "season", Season.ALL_YEAR.value)
        try:
            season = Season(season_text)
        except ValueError:
            resolver.problems.append(f"{entity}: unknown season {season_text!r}")
            continue

        offsets_resolved = resolver.resolve(entity, "offsets")
        if offsets_resolved is None:
            offsets: list[int | None] = [0, *([None] * (len(stop_ids) - 1))]
        else:
            offsets = list(offsets_resolved.value)
            if len(offsets) != len(stop_ids):
                resolver.problems.append(
                    f"{entity}: offsets has {len(offsets)} entries but the sequence has "
                    f"{len(stop_ids)}"
                )
                offsets = [0, *([None] * (len(stop_ids) - 1))]

        methods = _timing_methods(
            resolver.value(entity, "timing_methods", []),
            len(stop_ids),
            entity,
            resolver.problems,
        )

        stops = [
            PatternStop(
                stop_id=stop_id,
                offset_seconds=offset,
                timing_method=(
                    method if offset is not None else TimingMethod.UNKNOWN
                ),
            )
            for stop_id, offset, method in zip(stop_ids, offsets, methods, strict=True)
        ]

        declared_status = resolver.value(entity, "status")
        if declared_status is not None:
            try:
                status = PublicationStatus(declared_status)
            except ValueError:
                resolver.problems.append(f"{entity}: unknown status {declared_status!r}")
                status = PublicationStatus.NOT_PUBLISHABLE
        elif any(stop.offset_seconds is None for stop in stops):
            status = PublicationStatus.NOT_PUBLISHABLE
        else:
            status = PublicationStatus.PUBLISHABLE

        timing_model = None
        if offsets_resolved is not None:
            observation = offsets_resolved.observation
            source = evidence.source_of(observation)
            model_method = (
                TimingMethod.PUBLISHED
                if source.source_type is not SourceType.DERIVED
                else TimingMethod.OBSERVED_MEDIAN
            )
            # An explicit per-stop method list overrides the source-type guess.
            distinct = {m for m in methods if m is not TimingMethod.UNKNOWN}
            if len(distinct) == 1:
                model_method = distinct.pop()
            elif TimingMethod.OBSERVED_MEDIAN in distinct:
                model_method = TimingMethod.OBSERVED_MEDIAN
            elif TimingMethod.INTERPOLATED in distinct:
                model_method = TimingMethod.INTERPOLATED

            timing_model = _build_timing_model(model_method, observation)

        try:
            patterns.append(
                Pattern(
                    pattern_id=pattern_id,
                    route_id=route_id.value,
                    direction_id=resolver.value(entity, "direction_id", 0),
                    season=season,
                    headsign=headsign.value,
                    variant_code=resolver.value(entity, "variant_code"),
                    stops=stops,
                    shape_id=resolver.value(entity, "shape_id"),
                    timing_model=timing_model,
                    status=status,
                    conditional=resolver.value(entity, "conditional"),
                )
            )
        except ValueError as error:
            resolver.problems.append(f"{entity}: {error}")

    return sorted(patterns, key=lambda p: p.pattern_id), resolver.problems


def _build_timing_model(method: TimingMethod, observation: Observation) -> TimingModel:
    """Record how the offsets were arrived at, straight from the observation.

    The derivation is read from explicit fields rather than inferred from prose,
    so "estimated" can never quietly lose its qualifier on the way to GTFS.
    """
    description = observation.derivation or (
        "Read directly from the source's published timetable."
        if method is TimingMethod.PUBLISHED
        else "No derivation recorded."
    )
    return TimingModel(
        method=method,
        description=description,
        sample_size=observation.sample_size,
        derived_from=observation.derived_source_ids,
        computed_at=observation.retrieved_at,
    )
