"""Field registry: what each observed field means and how it is parsed.

Observations store every value as text so that the evidence file stays a plain,
diffable CSV. This module is the single place that says how a given
``(entity_type, field)`` is typed and which source hierarchy governs it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from almunecar_gtfs.provenance import Confidence, EvidenceDomain, EvidenceStore, Observation

LIST_SEPARATOR = ";"


class ParseError(ValueError):
    """An observed value does not match the shape its field requires."""


def parse_text(value: str) -> str:
    return value.strip()


def parse_int(value: str) -> int:
    try:
        return int(value.strip())
    except ValueError as error:
        raise ParseError(f"expected an integer, got {value!r}") from error


def parse_bool(value: str) -> bool:
    normalised = value.strip().casefold()
    if normalised in {"1", "true", "yes", "y", "si", "sí"}:
        return True
    if normalised in {"0", "false", "no", "n"}:
        return False
    raise ParseError(f"expected a boolean, got {value!r}")


def parse_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value.strip())
    except ValueError as error:
        raise ParseError(f"expected an ISO date (YYYY-MM-DD), got {value!r}") from error


def parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(LIST_SEPARATOR) if item.strip()]


def parse_int_list(value: str) -> list[int]:
    return [parse_int(item) for item in parse_list(value)]


def parse_optional_int_list(value: str) -> list[int | None]:
    """Offsets where an unknown entry is written as ``?``."""
    result: list[int | None] = []
    for item in parse_list(value):
        result.append(None if item == "?" else parse_int(item))
    return result


def parse_date_list(value: str) -> list[dt.date]:
    return [parse_date(item) for item in parse_list(value)]


def parse_coordinate(value: str) -> tuple[float, float]:
    """``"36.734012,-3.691004"`` in decimal degrees, latitude first.

    Latitude and longitude are one field on purpose: reconciling them separately
    would let a stop end up with one source's latitude and another's longitude.
    """
    parts = value.split(",")
    if len(parts) != 2:
        raise ParseError(f"expected 'lat,lon', got {value!r}")
    try:
        latitude, longitude = (float(part.strip()) for part in parts)
    except ValueError as error:
        raise ParseError(f"coordinate parts are not numbers: {value!r}") from error
    if not -90.0 <= latitude <= 90.0 or not -180.0 <= longitude <= 180.0:
        raise ParseError(f"coordinate outside WGS84 range: {value!r}")
    return latitude, longitude


def parse_times(value: str) -> list[str]:
    """A published departure list, e.g. ``"07:30;08:00;08:30"``."""
    times = []
    for item in parse_list(value):
        parts = item.split(":")
        if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
            raise ParseError(f"expected HH:MM or HH:MM:SS, got {item!r}")
        hours, minutes = int(parts[0]), int(parts[1])
        seconds = int(parts[2]) if len(parts) == 3 else 0
        if not (0 <= minutes < 60 and 0 <= seconds < 60):
            raise ParseError(f"invalid clock time: {item!r}")
        times.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
    return times


@dataclass(frozen=True)
class FieldSpec:
    domain: EvidenceDomain
    parse: Callable[[str], Any]
    description: str


SCHEDULE = EvidenceDomain.SCHEDULE
STOP_COORD = EvidenceDomain.STOP_COORD
GEOMETRY = EvidenceDomain.GEOMETRY

#: Every field a scraper is allowed to observe. Unknown fields are rejected so a
#: typo cannot quietly create a field nothing reads.
FIELD_SPECS: dict[tuple[str, str], FieldSpec] = {
    ("agency", "agency_name"): FieldSpec(SCHEDULE, parse_text, "Operator's trading name"),
    ("agency", "agency_url"): FieldSpec(SCHEDULE, parse_text, "Operator website"),
    ("agency", "agency_phone"): FieldSpec(SCHEDULE, parse_text, "Public telephone number"),
    ("agency", "agency_email"): FieldSpec(SCHEDULE, parse_text, "Public email address"),
    ("route", "route_short_name"): FieldSpec(SCHEDULE, parse_text, "Line designation, e.g. 2B"),
    ("route", "route_long_name"): FieldSpec(SCHEDULE, parse_text, "Full descriptive name"),
    ("route", "route_desc"): FieldSpec(SCHEDULE, parse_text, "Supplementary description"),
    ("route", "seasons"): FieldSpec(SCHEDULE, parse_list, "summer/winter/all_year"),
    ("route", "status"): FieldSpec(SCHEDULE, parse_text, "publishable/not_publishable/retired"),
    ("route", "former_short_names"): FieldSpec(
        SCHEDULE, parse_list, "Previous line numbers, recorded not assumed"
    ),
    ("stop", "name"): FieldSpec(SCHEDULE, parse_text, "Passenger-facing stop name"),
    ("stop", "coordinate"): FieldSpec(STOP_COORD, parse_coordinate, "lat,lon in WGS84"),
    ("stop", "municipality"): FieldSpec(SCHEDULE, parse_text, "Administrative municipality"),
    ("stop", "osm_node_id"): FieldSpec(SCHEDULE, parse_int, "OSM node id"),
    ("stop", "ibus_stop_id"): FieldSpec(SCHEDULE, parse_text, "iBusGPS internal stop id"),
    ("stop", "direction_hint"): FieldSpec(
        SCHEDULE, parse_text, "Which side of the road / direction served"
    ),
    ("stop", "pair_stop_id"): FieldSpec(SCHEDULE, parse_text, "Opposite-direction stop"),
    ("stop", "status"): FieldSpec(
        SCHEDULE, parse_text, "publishable/not_publishable/retired"
    ),
    ("pattern", "route_id"): FieldSpec(SCHEDULE, parse_text, "Owning route"),
    ("pattern", "direction_id"): FieldSpec(SCHEDULE, parse_int, "0 outbound, 1 inbound"),
    ("pattern", "season"): FieldSpec(SCHEDULE, parse_text, "summer/winter/all_year"),
    ("pattern", "headsign"): FieldSpec(SCHEDULE, parse_text, "Destination shown to passengers"),
    ("pattern", "variant_code"): FieldSpec(SCHEDULE, parse_text, "Discriminator, e.g. CABRIA"),
    ("pattern", "stop_sequence"): FieldSpec(
        SCHEDULE, parse_list, "Ordered internal stop ids, ';' separated"
    ),
    ("pattern", "offsets"): FieldSpec(
        SCHEDULE, parse_optional_int_list, "Seconds after origin per stop; '?' when unknown"
    ),
    ("pattern", "timing_methods"): FieldSpec(
        SCHEDULE, parse_list, "Per-stop timing method, parallel to stop_sequence"
    ),
    ("pattern", "shape_id"): FieldSpec(SCHEDULE, parse_text, "Geometry used by this pattern"),
    ("pattern", "conditional"): FieldSpec(
        SCHEDULE, parse_text, "When this variant runs, if not the standard case"
    ),
    ("pattern", "status"): FieldSpec(SCHEDULE, parse_text, "publishable/not_publishable/retired"),
    ("service", "weekdays"): FieldSpec(
        SCHEDULE, parse_list, "Any of mon,tue,wed,thu,fri,sat,sun"
    ),
    ("service", "start_date"): FieldSpec(SCHEDULE, parse_date, "First day of the period"),
    ("service", "end_date"): FieldSpec(SCHEDULE, parse_date, "Last day of the period"),
    ("service", "added_dates"): FieldSpec(SCHEDULE, parse_date_list, "calendar_dates additions"),
    ("service", "removed_dates"): FieldSpec(SCHEDULE, parse_date_list, "calendar_dates removals"),
    ("service", "description"): FieldSpec(SCHEDULE, parse_text, "Human description of the period"),
    ("shape", "geometry"): FieldSpec(
        GEOMETRY, parse_text, "Path to a GeoJSON LineString under data/evidence/geometry/"
    ),
}

#: ``departures:<service_id>`` on a pattern entity holds that service's published
#: origin departure times. Handled separately because the service id is part of
#: the field name.
DEPARTURES_PREFIX = "departures:"
DEPARTURES_SPEC = FieldSpec(
    SCHEDULE, parse_times, "Published origin departures for one service period"
)


def spec_for(entity_type: str, field: str) -> FieldSpec:
    if field.startswith(DEPARTURES_PREFIX):
        return DEPARTURES_SPEC
    try:
        return FIELD_SPECS[(entity_type, field)]
    except KeyError:
        raise ParseError(f"unknown field {field!r} for entity type {entity_type!r}") from None


def domain_for(entity: str, field: str) -> EvidenceDomain:
    """:class:`~almunecar_gtfs.provenance.DomainResolver` implementation."""
    entity_type = entity.split(":", 1)[0]
    try:
        return spec_for(entity_type, field).domain
    except ParseError:
        return SCHEDULE


@dataclass(frozen=True)
class Resolved:
    """A parsed winning value together with the observation that produced it."""

    value: Any
    observation: Observation

    @property
    def source_id(self) -> str:
        return self.observation.source_id

    @property
    def confidence(self) -> Confidence:
        return self.observation.confidence


class Resolver:
    """Turns evidence into typed canonical values, collecting problems as it goes."""

    def __init__(self, evidence: EvidenceStore) -> None:
        self.evidence = evidence
        self.problems: list[str] = []

    def resolve(self, entity: str, field: str) -> Resolved | None:
        """Best available value for a field, or ``None`` if nothing qualifies."""
        entity_type = entity.split(":", 1)[0]
        try:
            spec = spec_for(entity_type, field)
        except ParseError as error:
            self.problems.append(f"{entity}/{field}: {error}")
            return None
        observation = self.evidence.best(spec.domain, entity, field)
        if observation is None:
            return None
        try:
            return Resolved(value=spec.parse(observation.value), observation=observation)
        except ParseError as error:
            self.problems.append(f"{entity}/{field} from {observation.source_id}: {error}")
            return None

    def require(self, entity: str, field: str) -> Resolved | None:
        resolved = self.resolve(entity, field)
        if resolved is None:
            self.problems.append(f"{entity}: no usable evidence for required field {field!r}")
        return resolved

    def value(self, entity: str, field: str, default: Any = None) -> Any:
        resolved = self.resolve(entity, field)
        return default if resolved is None else resolved.value

    def fields_of(self, entity: str, prefix: str) -> list[str]:
        """Every observed field on ``entity`` beginning with ``prefix``."""
        return sorted(
            {
                observation.field
                for observation in self.evidence.observations
                if observation.entity == entity and observation.field.startswith(prefix)
            }
        )
