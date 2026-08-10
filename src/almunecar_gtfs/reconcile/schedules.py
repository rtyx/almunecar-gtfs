"""Reconcile observations into service periods and scheduled departures.

The operator publishes departures from the principal stop rather than a time for
every intermediate stop. Those origin departures live here; the per-stop offsets
that turn them into ``stop_times.txt`` live on the pattern, together with the
method used to derive them.
"""

from __future__ import annotations

from collections.abc import Sequence

from almunecar_gtfs.models import Pattern, ServicePeriod, TripDeparture
from almunecar_gtfs.provenance import EvidenceStore
from almunecar_gtfs.reconcile.fields import DEPARTURES_PREFIX, Resolver

WEEKDAY_FIELDS: tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

WEEKDAY_TOKENS: dict[str, str] = {
    "mon": "monday",
    "tue": "tuesday",
    "wed": "wednesday",
    "thu": "thursday",
    "fri": "friday",
    "sat": "saturday",
    "sun": "sunday",
}


def reconcile_services(evidence: EvidenceStore) -> tuple[list[ServicePeriod], list[str]]:
    resolver = Resolver(evidence)
    services: list[ServicePeriod] = []

    for entity in evidence.entities("service"):
        service_id = entity.split(":", 1)[1]
        start = resolver.require(entity, "start_date")
        end = resolver.require(entity, "end_date")
        if start is None or end is None:
            continue

        flags = dict.fromkeys(WEEKDAY_FIELDS, False)
        for token in resolver.value(entity, "weekdays", []):
            key = WEEKDAY_TOKENS.get(token.strip().casefold()[:3])
            if key is None:
                resolver.problems.append(f"{entity}: unknown weekday token {token!r}")
                continue
            flags[key] = True

        try:
            services.append(
                ServicePeriod(
                    service_id=service_id,
                    **flags,
                    start_date=start.value,
                    end_date=end.value,
                    description=resolver.value(entity, "description"),
                    added_dates=resolver.value(entity, "added_dates", []),
                    removed_dates=resolver.value(entity, "removed_dates", []),
                )
            )
        except ValueError as error:
            resolver.problems.append(f"{entity}: {error}")

    return sorted(services, key=lambda s: s.service_id), resolver.problems


def make_trip_id(pattern: Pattern, service_id: str, departure: str) -> str:
    """Stable, readable and collision-free, e.g. ``ALM_2B_SUMMER_WD_OUT_0830``.

    Composed from meaning rather than position, so inserting a departure does
    not renumber every trip after it.
    """
    hours, minutes = departure.split(":")[:2]
    direction = "OUT" if pattern.direction_id == 0 else "IN"
    parts = [pattern.route_id, service_id, direction]
    if pattern.variant_code:
        parts.append(pattern.variant_code)
    parts.append(f"{int(hours):02d}{minutes}")
    return "_".join(parts)


def reconcile_trips(
    evidence: EvidenceStore,
    patterns: Sequence[Pattern],
    service_ids: set[str],
) -> tuple[list[TripDeparture], list[str]]:
    resolver = Resolver(evidence)
    trips: list[TripDeparture] = []
    seen: set[str] = set()

    for pattern in patterns:
        entity = f"pattern:{pattern.pattern_id}"
        for field in resolver.fields_of(entity, DEPARTURES_PREFIX):
            service_id = field[len(DEPARTURES_PREFIX) :]
            if service_id not in service_ids:
                resolver.problems.append(
                    f"{entity}: departures reference unknown service {service_id!r}"
                )
                continue
            resolved = resolver.resolve(entity, field)
            if resolved is None:
                continue
            for departure in resolved.value:
                trip_id = make_trip_id(pattern, service_id, departure)
                if trip_id in seen:
                    resolver.problems.append(
                        f"{entity}: duplicate departure {departure} for {service_id} "
                        f"(trip id {trip_id})"
                    )
                    continue
                seen.add(trip_id)
                trips.append(
                    TripDeparture(
                        trip_id=trip_id,
                        pattern_id=pattern.pattern_id,
                        service_id=service_id,
                        departure=departure,
                        source_id=resolved.source_id,
                    )
                )

    return sorted(trips, key=lambda t: t.trip_id), resolver.problems
