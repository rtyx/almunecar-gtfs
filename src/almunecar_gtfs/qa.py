"""Invariant checks over the canonical dataset.

These live in the library rather than only in tests so that the CLI can report
them to a human reviewer, CI can fail on them, and the QA map can colour stops
by the flags they raise. ``tests/`` drives the same functions.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from almunecar_gtfs.models import (
    DISTINCT_STOP_MIN_DISTANCE_M,
    SAME_NAME_DISTANCE_WARN_M,
    SERVICE_AREA_BBOX,
    Network,
    PublicationStatus,
    TimingMethod,
)
from almunecar_gtfs.provenance import EvidenceDomain, EvidenceStore, SourceType

#: A published shape should pass within this distance of each of its stops.
SHAPE_STOP_WARN_M = 50.0
SHAPE_STOP_ERROR_M = 200.0

#: Gaps between consecutive shape points. Urban geometry densified from roads
#: should never leap; a long jump means the shape was stitched badly.
SHAPE_SEGMENT_WARN_M = 300.0
SHAPE_SEGMENT_ERROR_M = 1_500.0

#: Google Transit requires the feed to cover at least four weeks ahead.
REQUIRED_FUTURE_HORIZON_DAYS = 28


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Severity
    code: str
    entity: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper():7}] {self.code:28} {self.entity}: {self.message}"


def errors(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity is Severity.ERROR]


def warnings(findings: Iterable[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity is Severity.WARNING]


# -- stops ---------------------------------------------------------------


def check_stops(network: Network) -> list[Finding]:
    found: list[Finding] = []
    seen: dict[str, int] = defaultdict(int)
    for stop in network.stops:
        seen[stop.internal_stop_id] += 1
    for stop_id, count in sorted(seen.items()):
        if count > 1:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="stop.duplicate_id",
                    entity=f"stop:{stop_id}",
                    message=f"{count} stop records share this id",
                )
            )

    min_lat, min_lon, max_lat, max_lon = SERVICE_AREA_BBOX
    for stop in network.stops:
        if not stop.in_service_area:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="stop.outside_service_area",
                    entity=f"stop:{stop.internal_stop_id}",
                    message=(
                        f"({stop.latitude:.6f}, {stop.longitude:.6f}) is outside the "
                        f"service-area box ({min_lat}, {min_lon})-({max_lat}, {max_lon})"
                    ),
                )
            )

    by_name: dict[str, list] = defaultdict(list)
    for stop in network.stops:
        by_name[stop.name.strip().casefold()].append(stop)
    for name, group in sorted(by_name.items()):
        for index, first in enumerate(group):
            for second in group[index + 1 :]:
                distance = first.distance_to(second)
                if distance > SAME_NAME_DISTANCE_WARN_M:
                    found.append(
                        Finding(
                            severity=Severity.WARNING,
                            code="stop.same_name_far_apart",
                            entity=f"stop:{first.internal_stop_id}",
                            message=(
                                f"shares the name {name!r} with {second.internal_stop_id} "
                                f"but is {distance:.0f} m away; confirm they are really "
                                f"two places and not a mis-sourced coordinate"
                            ),
                        )
                    )

    ordered = sorted(network.stops, key=lambda s: s.internal_stop_id)
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            distance = first.distance_to(second)
            if distance < DISTINCT_STOP_MIN_DISTANCE_M:
                found.append(
                    Finding(
                        severity=Severity.WARNING,
                        code="stop.near_duplicate",
                        entity=f"stop:{first.internal_stop_id}",
                        message=(
                            f"only {distance:.1f} m from {second.internal_stop_id} "
                            f"({second.name!r}); likely one physical stop recorded twice"
                        ),
                    )
                )

    for stop in network.stops:
        if stop.pair_stop_id is None:
            continue
        partner = network.stops_by_id.get(stop.pair_stop_id)
        if partner is None:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="stop.pair_missing",
                    entity=f"stop:{stop.internal_stop_id}",
                    message=f"pair_stop_id {stop.pair_stop_id} does not exist",
                )
            )
        elif partner.pair_stop_id != stop.internal_stop_id:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="stop.pair_not_reciprocal",
                    entity=f"stop:{stop.internal_stop_id}",
                    message=f"{stop.pair_stop_id} does not point back at this stop",
                )
            )
    return found


# -- routes and patterns -------------------------------------------------


def check_routes(network: Network) -> list[Finding]:
    found: list[Finding] = []
    route_ids = set(network.routes_by_id)
    if len(route_ids) != len(network.routes):
        found.append(
            Finding(
                severity=Severity.ERROR,
                code="route.duplicate_id",
                entity="routes",
                message="duplicate route_id in routes.yaml",
            )
        )

    patterns_by_route: dict[str, int] = defaultdict(int)
    for pattern in network.patterns:
        patterns_by_route[pattern.route_id] += 1
        if pattern.route_id not in route_ids:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="pattern.unknown_route",
                    entity=f"pattern:{pattern.pattern_id}",
                    message=f"references unknown route {pattern.route_id}",
                )
            )

    trips_by_pattern: dict[str, int] = defaultdict(int)
    for trip in network.trips:
        trips_by_pattern[trip.pattern_id] += 1

    for route in network.routes:
        if route.status is not PublicationStatus.PUBLISHABLE:
            # A route we have deliberately excluded owes us nothing further; the
            # reason it is excluded is recorded on the route itself.
            continue
        pattern_ids = [p.pattern_id for p in network.patterns if p.route_id == route.route_id]
        if not pattern_ids:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="route.no_patterns",
                    entity=f"route:{route.route_id}",
                    message="route has no patterns",
                )
            )
            continue
        if not any(trips_by_pattern[pattern_id] for pattern_id in pattern_ids):
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="route.no_trips",
                    entity=f"route:{route.route_id}",
                    message="route has patterns but no scheduled trips",
                )
            )
    return found


def check_patterns(network: Network) -> list[Finding]:
    found: list[Finding] = []
    stop_ids = set(network.stops_by_id)
    shape_ids = set(network.shapes_by_id)
    seen: set[str] = set()

    for pattern in network.patterns:
        if pattern.pattern_id in seen:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="pattern.duplicate_id",
                    entity=f"pattern:{pattern.pattern_id}",
                    message="duplicate pattern_id",
                )
            )
        seen.add(pattern.pattern_id)

        for missing in sorted(set(pattern.stop_ids) - stop_ids):
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="pattern.unknown_stop",
                    entity=f"pattern:{pattern.pattern_id}",
                    message=f"references unknown stop {missing}",
                )
            )

        if pattern.shape_id is not None and pattern.shape_id not in shape_ids:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="pattern.unknown_shape",
                    entity=f"pattern:{pattern.pattern_id}",
                    message=f"references unknown shape {pattern.shape_id}",
                )
            )
        elif pattern.shape_id is None and pattern.status is PublicationStatus.PUBLISHABLE:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="pattern.no_shape",
                    entity=f"pattern:{pattern.pattern_id}",
                    message="publishable pattern has no shape; passengers get straight lines",
                )
            )

        if not pattern.has_complete_timings and pattern.status is PublicationStatus.PUBLISHABLE:
            unknown = [s.stop_id for s in pattern.stops if s.offset_seconds is None]
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="pattern.incomplete_timings",
                    entity=f"pattern:{pattern.pattern_id}",
                    message=(
                        f"marked publishable but {len(unknown)} stop(s) have no offset "
                        f"({', '.join(unknown[:5])}); mark it not_publishable instead of "
                        f"inventing times"
                    ),
                )
            )

        if (
            pattern.has_complete_timings
            and not pattern.has_anchored_endpoints
            and pattern.status is PublicationStatus.PUBLISHABLE
        ):
            ends = [
                f"{pattern.stops[0].stop_id} ({pattern.stops[0].timing_method})",
                f"{pattern.stops[-1].stop_id} ({pattern.stops[-1].timing_method})",
            ]
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="pattern.unanchored_endpoints",
                    entity=f"pattern:{pattern.pattern_id}",
                    message=(
                        f"first/last calls are not published timepoints: {', '.join(ends)}. "
                        f"GTFS requires real times at both ends of a trip; an estimate "
                        f"there is a claim about when the service starts and finishes, "
                        f"not a marked approximation"
                    ),
                )
            )

        if pattern.timing_model is None and pattern.has_complete_timings:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="pattern.no_timing_model",
                    entity=f"pattern:{pattern.pattern_id}",
                    message="has offsets but records no derivation method",
                )
            )

        derived = [
            stop
            for stop in pattern.stops
            if stop.timing_method
            in (TimingMethod.OBSERVED_MEDIAN, TimingMethod.INTERPOLATED)
        ]
        if derived and pattern.timing_model is not None:
            model = pattern.timing_model
            if model.method is TimingMethod.OBSERVED_MEDIAN and not model.sample_size:
                found.append(
                    Finding(
                        severity=Severity.ERROR,
                        code="pattern.median_without_samples",
                        entity=f"pattern:{pattern.pattern_id}",
                        message="observed_median timings must record how many runs were used",
                    )
                )
            if not model.derived_from:
                found.append(
                    Finding(
                        severity=Severity.WARNING,
                        code="pattern.derivation_without_sources",
                        entity=f"pattern:{pattern.pattern_id}",
                        message="derived timings list no source ids",
                    )
                )
    return found


def check_trips(network: Network) -> list[Finding]:
    found: list[Finding] = []
    patterns = network.patterns_by_id
    services = network.services_by_id
    seen: set[str] = set()

    for trip in network.trips:
        if trip.trip_id in seen:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="trip.duplicate_id",
                    entity=f"trip:{trip.trip_id}",
                    message="duplicate trip_id",
                )
            )
        seen.add(trip.trip_id)

        pattern = patterns.get(trip.pattern_id)
        if pattern is None:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="trip.unknown_pattern",
                    entity=f"trip:{trip.trip_id}",
                    message=f"references unknown pattern {trip.pattern_id}",
                )
            )
        elif len(pattern.stops) < 2:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="trip.too_few_stops",
                    entity=f"trip:{trip.trip_id}",
                    message=f"pattern {pattern.pattern_id} has fewer than two stops",
                )
            )

        if trip.service_id not in services:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="trip.unknown_service",
                    entity=f"trip:{trip.trip_id}",
                    message=f"references unknown service {trip.service_id}",
                )
            )
    return found


# -- calendars -----------------------------------------------------------


def check_calendars(
    network: Network, today: dt.date | None = None, horizon_days: int = REQUIRED_FUTURE_HORIZON_DAYS
) -> list[Finding]:
    found: list[Finding] = []
    today = today or dt.date.today()
    horizon_end = today + dt.timedelta(days=horizon_days)

    used_services = {trip.service_id for trip in network.publishable_trips()}
    active = [s for s in network.services if s.service_id in used_services]

    for service in network.services:
        if not service.runs_on_some_day:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="service.never_runs",
                    entity=f"service:{service.service_id}",
                    message="no weekday flags and no added dates",
                )
            )
        if service.service_id not in used_services:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="service.unused",
                    entity=f"service:{service.service_id}",
                    message="no publishable trip references this service",
                )
            )

    if not active:
        # When nothing is publishable the cause lies upstream, and
        # `check_readiness` names it. Reporting it here as well would bury the
        # real reason under a symptom.
        blocked = any(not p.is_publishable for p in network.patterns)
        found.append(
            Finding(
                severity=Severity.WARNING if blocked else Severity.ERROR,
                code="calendar.no_active_service",
                entity="calendar",
                message=(
                    "no publishable trip references any service period"
                    + (" (see the readiness findings for why)" if blocked else "")
                ),
            )
        )
        return found

    latest_end = max(service.end_date for service in active)
    if latest_end < horizon_end:
        found.append(
            Finding(
                severity=Severity.ERROR,
                code="calendar.horizon_too_short",
                entity="calendar",
                message=(
                    f"service ends {latest_end}, short of the required {horizon_days}-day "
                    f"horizon ({horizon_end}); Google Transit rejects feeds that expire"
                ),
            )
        )

    uncovered: list[dt.date] = []
    day = today
    while day <= min(horizon_end, latest_end):
        if not any(service.covers(day) for service in active):
            uncovered.append(day)
        day += dt.timedelta(days=1)
    if uncovered:
        found.append(
            Finding(
                severity=Severity.WARNING,
                code="calendar.gap",
                entity="calendar",
                message=(
                    f"{len(uncovered)} day(s) inside the horizon have no service at all, "
                    f"starting {uncovered[0]}; check the summer/winter boundary"
                ),
            )
        )
    return found


# -- geometry ------------------------------------------------------------


def check_geometry(network: Network) -> list[Finding]:
    found: list[Finding] = []
    stops = network.stops_by_id

    for shape in network.shapes:
        longest = shape.max_segment_m()
        if longest > SHAPE_SEGMENT_ERROR_M:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="shape.implausible_jump",
                    entity=f"shape:{shape.shape_id}",
                    message=f"contains a {longest:.0f} m gap between consecutive points",
                )
            )
        elif longest > SHAPE_SEGMENT_WARN_M:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="shape.sparse_segment",
                    entity=f"shape:{shape.shape_id}",
                    message=f"longest segment is {longest:.0f} m; geometry may be too coarse",
                )
            )

    for pattern in network.patterns:
        shape = network.shapes_by_id.get(pattern.shape_id or "")
        if shape is None:
            continue
        for stop_id in pattern.stop_ids:
            stop = stops.get(stop_id)
            if stop is None:
                continue
            distance = shape.distance_to_point_m(stop.latitude, stop.longitude)
            if distance > SHAPE_STOP_ERROR_M:
                severity = Severity.ERROR
                code = "shape.stop_far_from_shape"
            elif distance > SHAPE_STOP_WARN_M:
                severity = Severity.WARNING
                code = "shape.stop_off_shape"
            else:
                continue
            found.append(
                Finding(
                    severity=severity,
                    code=code,
                    entity=f"pattern:{pattern.pattern_id}",
                    message=f"{stop_id} is {distance:.0f} m from shape {shape.shape_id}",
                )
            )
    return found


# -- provenance ----------------------------------------------------------


def check_provenance(network: Network, evidence: EvidenceStore) -> list[Finding]:
    """Every canonical fact must trace back to a registered source."""
    found: list[Finding] = []
    known_sources = set(evidence.sources)

    for stop in network.stops:
        entity = f"stop:{stop.internal_stop_id}"
        if stop.source_id not in known_sources:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="provenance.unknown_source",
                    entity=entity,
                    message=f"coordinate cites unregistered source {stop.source_id!r}",
                )
            )
        if not evidence.for_field(entity, "coordinate"):
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="provenance.stop_coordinate",
                    entity=entity,
                    message="no observation backs this coordinate",
                )
            )

    for route in network.routes:
        entity = f"route:{route.route_id}"
        if not evidence.for_field(entity, "route_short_name"):
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="provenance.route",
                    entity=entity,
                    message="no observation backs this route's short name",
                )
            )

    for pattern in network.patterns:
        entity = f"pattern:{pattern.pattern_id}"
        if not evidence.for_field(entity, "stop_sequence"):
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="provenance.pattern_sequence",
                    entity=entity,
                    message="no observation backs this stop sequence",
                )
            )

    for trip in network.trips:
        source = evidence.sources.get(trip.source_id)
        if source is None:
            found.append(
                Finding(
                    severity=Severity.ERROR,
                    code="provenance.unknown_source",
                    entity=f"trip:{trip.trip_id}",
                    message=f"departure cites unregistered source {trip.source_id!r}",
                )
            )
        elif source.source_type in (SourceType.MOOVIT, SourceType.OSM):
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="provenance.weak_departure_source",
                    entity=f"trip:{trip.trip_id}",
                    message=(
                        f"departure rests on {source.source_type}, which is a QA reference "
                        f"rather than an authority on the operator's timetable"
                    ),
                )
            )

    # Published (exact) times must come from a schedule-domain authority.
    for pattern in network.patterns:
        published = [s for s in pattern.stops if s.timing_method is TimingMethod.PUBLISHED]
        if not published:
            continue
        best = evidence.best(EvidenceDomain.SCHEDULE, f"pattern:{pattern.pattern_id}", "offsets")
        if best is None:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="provenance.published_timing",
                    entity=f"pattern:{pattern.pattern_id}",
                    message=(
                        f"{len(published)} stop(s) are marked as published timepoints but no "
                        f"offsets observation was recorded"
                    ),
                )
            )

    published_routes = {f"route:{p.route_id}" for p in network.publishable_patterns()}
    published_patterns = {f"pattern:{p.pattern_id}" for p in network.publishable_patterns()}
    reaching_the_feed = published_routes | published_patterns

    for entity in sorted(evidence.blocking_entities()):
        # A block that is being honoured is the system working, not a defect.
        # It only becomes an error if the entity is in the feed anyway.
        escaped = entity in reaching_the_feed
        found.append(
            Finding(
                severity=Severity.ERROR if escaped else Severity.WARNING,
                code="provenance.blocking_conflict",
                entity=entity,
                message=(
                    "an unresolved conflict marked blocks_publication still stands, and this "
                    "entity is in the feed anyway"
                    if escaped
                    else "held out of the feed by an unresolved blocks_publication conflict"
                ),
            )
        )
    return found


def check_readiness(network: Network) -> list[Finding]:
    """Say plainly what is keeping the dataset out of a feed.

    A research-stage dataset is not a broken one. These findings are warnings so
    that CI stays meaningful, but they name the exact blocker per pattern rather
    than letting an empty feed look like a mysterious failure.
    """
    found: list[Finding] = []
    for pattern in sorted(network.patterns, key=lambda p: p.pattern_id):
        if pattern.is_publishable:
            continue
        entity = f"pattern:{pattern.pattern_id}"
        unknown = [s.stop_id for s in pattern.stops if s.offset_seconds is None]
        if not unknown and not pattern.has_anchored_endpoints:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="readiness.unanchored_endpoints",
                    entity=entity,
                    message=(
                        "every stop has an offset, but the first and/or last call is an "
                        "estimate. GTFS needs real times at both ends before this can ship."
                    ),
                )
            )
            continue
        # Missing timings are reported first: they are why reconciliation set the
        # status, so leading with "excluded by decision" would hide the cause.
        if unknown:
            found.append(
                Finding(
                    severity=Severity.WARNING,
                    code="readiness.no_intermediate_timings",
                    entity=entity,
                    message=(
                        f"{len(unknown)} of {len(pattern.stops)} stops have no offset from "
                        f"the origin departure. The operator publishes only departures from "
                        f"the principal stop, so these cannot be filled without observed runs."
                    ),
                )
            )
            continue
        found.append(
            Finding(
                severity=Severity.WARNING,
                code="readiness.pattern_excluded",
                entity=entity,
                message=f"marked {pattern.status}; excluded from the feed by decision",
            )
        )

    if network.patterns and not network.publishable_patterns():
        found.append(
            Finding(
                severity=Severity.WARNING,
                code="readiness.feed_not_buildable",
                entity="feed",
                message=(
                    "No pattern is publishable, so no GTFS feed can be built. This is the "
                    "documented research-stage state, not a regression: see "
                    "docs/methodology.md on timings."
                ),
            )
        )
    return found


def check_all(
    network: Network,
    evidence: EvidenceStore | None = None,
    today: dt.date | None = None,
) -> list[Finding]:
    found = [
        *check_stops(network),
        *check_routes(network),
        *check_patterns(network),
        *check_trips(network),
        *check_calendars(network, today=today),
        *check_geometry(network),
        *check_readiness(network),
    ]
    if evidence is not None:
        found.extend(check_provenance(network, evidence))
    return found
