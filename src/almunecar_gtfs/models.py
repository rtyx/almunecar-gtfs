"""Canonical models for the Almunecar urban bus network.

This module answers the project's second question: *what do we believe the
canonical network actually is?* Canonical objects are produced only by
:mod:`almunecar_gtfs.reconcile` from reconciled evidence, and are the sole input
to GTFS generation.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from almunecar_gtfs.provenance import Confidence

STOP_ID_PATTERN = re.compile(r"^ALM_\d{4}$")

#: Generous bounding box around Almunecar, La Herradura, Torrecuevas, Taramay and
#: Cabria. Anything outside it is a research error, not a bus stop.
SERVICE_AREA_BBOX = (36.68, -3.80, 36.83, -3.60)  # min_lat, min_lon, max_lat, max_lon

#: Two stops sharing a name but further apart than this are probably distinct
#: places rather than a direction pair, and are worth a human look.
SAME_NAME_DISTANCE_WARN_M = 100.0

#: Two distinct stop ids closer together than this are probably a duplicate.
DISTINCT_STOP_MIN_DISTANCE_M = 10.0

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


class Season(StrEnum):
    """The operator's two published service periods, plus special sub-periods."""

    SUMMER = "summer"
    WINTER = "winter"
    ALL_YEAR = "all_year"


class PublicationStatus(StrEnum):
    """Whether an entity is fit to appear in the published feed."""

    PUBLISHABLE = "publishable"
    NOT_PUBLISHABLE = "not_publishable"
    """Evidence is too thin to publish. Excluded from the GTFS build."""

    RETIRED = "retired"
    """Historically real, no longer operating. Kept for the record, not published."""


class TimingMethod(StrEnum):
    """How an intermediate stop time was arrived at."""

    PUBLISHED = "published"
    """Read directly from an authoritative timetable. GTFS ``timepoint=1``."""

    OBSERVED_MEDIAN = "observed_median"
    """Median offset across several recorded runs. GTFS ``timepoint=0``."""

    INTERPOLATED = "interpolated"
    """Interpolated between two published timepoints. GTFS ``timepoint=0``."""

    UNKNOWN = "unknown"
    """No defensible basis. Renders the pattern not publishable."""


class Agency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agency_id: str
    agency_name: str
    agency_url: str
    agency_timezone: str = "Europe/Madrid"
    agency_lang: str = "es"
    agency_phone: str | None = None
    agency_email: str | None = None
    is_official_feed: bool = False
    """False until the operator authorises publication. Drives README wording."""


class Stop(BaseModel):
    """One physical boarding location.

    Two poles on opposite sides of the same road are two stops, even when the
    operator prints the same name on both.
    """

    model_config = ConfigDict(extra="forbid")

    internal_stop_id: str
    name: str
    latitude: float
    longitude: float
    municipality: str
    confidence: Confidence
    source_id: str
    """The observation source that established the coordinate."""

    osm_node_id: int | None = None
    ibus_stop_id: str | None = None
    direction_hint: str | None = None
    """e.g. ``towards La Herradura``. Distinguishes the two poles of a pair."""

    pair_stop_id: str | None = None
    """The opposite-direction stop, when one exists."""

    status: PublicationStatus = PublicationStatus.PUBLISHABLE
    notes: str | None = None

    @field_validator("internal_stop_id")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        if not STOP_ID_PATTERN.match(value):
            raise ValueError(f"stop id must look like ALM_0001, got {value!r}")
        return value

    @field_validator("latitude")
    @classmethod
    def _valid_latitude(cls, value: float) -> float:
        if not -90.0 <= value <= 90.0:
            raise ValueError(f"latitude out of WGS84 range: {value}")
        return value

    @field_validator("longitude")
    @classmethod
    def _valid_longitude(cls, value: float) -> float:
        if not -180.0 <= value <= 180.0:
            raise ValueError(f"longitude out of WGS84 range: {value}")
        return value

    @property
    def in_service_area(self) -> bool:
        min_lat, min_lon, max_lat, max_lon = SERVICE_AREA_BBOX
        return min_lat <= self.latitude <= max_lat and min_lon <= self.longitude <= max_lon

    def distance_to(self, other: Stop) -> float:
        return haversine_m(self.latitude, self.longitude, other.latitude, other.longitude)


class Route(BaseModel):
    """A passenger-facing route.

    ``route_id`` stays stable across seasons when the route means the same thing
    to a passenger; seasonal differences live in patterns and calendars.
    """

    model_config = ConfigDict(extra="forbid")

    route_id: str
    route_short_name: str
    route_long_name: str
    route_type: int = 3
    route_desc: str | None = None
    route_color: str | None = None
    route_text_color: str | None = None
    seasons: list[Season] = Field(default_factory=list)
    status: PublicationStatus = PublicationStatus.PUBLISHABLE
    former_short_names: list[str] = Field(default_factory=list)
    """Recorded, never assumed. A stale page calling Torrecuevas "5" belongs here
    only once the current designation has actually been established."""

    notes: str | None = None

    @field_validator("route_type")
    @classmethod
    def _valid_route_type(cls, value: int) -> int:
        allowed = {0, 1, 2, 3, 4, 5, 6, 7, 11, 12}
        if value not in allowed:
            raise ValueError(f"invalid GTFS route_type: {value}")
        return value


class PatternStop(BaseModel):
    """One call within a pattern, with its timing basis."""

    model_config = ConfigDict(extra="forbid")

    stop_id: str
    offset_seconds: int | None = None
    """Seconds after the trip's origin departure. ``None`` means unknown."""

    timing_method: TimingMethod = TimingMethod.UNKNOWN
    stop_headsign: str | None = None
    request_stop: bool = False
    """Served on request only; mapped to GTFS ``pickup_type``/``drop_off_type`` 3."""

    notes: str | None = None

    @property
    def is_timepoint(self) -> bool:
        return self.timing_method is TimingMethod.PUBLISHED


class TimingModel(BaseModel):
    """How a pattern's intermediate times were derived, recorded per pattern.

    Kept separate from the offsets themselves so the method survives even when
    the numbers are later refined.
    """

    model_config = ConfigDict(extra="forbid")

    method: TimingMethod
    description: str
    sample_size: int | None = None
    """Number of observed runs behind ``observed_median`` offsets."""

    derived_from: list[str] = Field(default_factory=list)
    """Source ids the derivation consumed."""

    computed_at: dt.date | None = None


class Pattern(BaseModel):
    """One ordered stop sequence actually operated.

    Modelled instead of bare "routes" because 2A outbound, 2B inbound and the
    3B Cabria extension are different sequences that happen to share signage.
    """

    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    route_id: str
    direction_id: int = Field(ge=0, le=1)
    season: Season
    headsign: str
    variant_code: str | None = None
    """Short discriminator when a route runs more than one sequence in the same
    direction and season, e.g. ``CABRIA``. Keeps generated trip ids stable and
    collision-free rather than positional."""

    stops: list[PatternStop] = Field(min_length=2)
    shape_id: str | None = None
    timing_model: TimingModel | None = None
    status: PublicationStatus = PublicationStatus.PUBLISHABLE
    conditional: str | None = None
    """Prose describing when this variant runs, if it is not the standard case."""

    notes: str | None = None

    @model_validator(mode="after")
    def _origin_is_zero(self) -> Self:
        first = self.stops[0]
        if first.offset_seconds not in (0, None):
            raise ValueError(
                f"{self.pattern_id}: first stop offset must be 0, got {first.offset_seconds}"
            )
        return self

    @model_validator(mode="after")
    def _offsets_never_go_backwards(self) -> Self:
        previous: int | None = None
        for stop in self.stops:
            if stop.offset_seconds is None:
                continue
            if previous is not None and stop.offset_seconds < previous:
                raise ValueError(
                    f"{self.pattern_id}: offsets move backwards at {stop.stop_id} "
                    f"({stop.offset_seconds} < {previous})"
                )
            previous = stop.offset_seconds
        return self

    @model_validator(mode="after")
    def _no_immediate_repeats(self) -> Self:
        for earlier, later in zip(self.stops, self.stops[1:], strict=False):
            if earlier.stop_id == later.stop_id:
                raise ValueError(f"{self.pattern_id}: stop {earlier.stop_id} repeats consecutively")
        return self

    @property
    def stop_ids(self) -> list[str]:
        return [stop.stop_id for stop in self.stops]

    @property
    def has_complete_timings(self) -> bool:
        return all(stop.offset_seconds is not None for stop in self.stops)

    @property
    def is_publishable(self) -> bool:
        return self.status is PublicationStatus.PUBLISHABLE and self.has_complete_timings


class ServicePeriod(BaseModel):
    """A GTFS ``calendar.txt`` entry plus its exceptions."""

    model_config = ConfigDict(extra="forbid")

    service_id: str
    monday: bool = False
    tuesday: bool = False
    wednesday: bool = False
    thursday: bool = False
    friday: bool = False
    saturday: bool = False
    sunday: bool = False
    start_date: dt.date
    end_date: dt.date
    description: str | None = None
    added_dates: list[dt.date] = Field(default_factory=list)
    removed_dates: list[dt.date] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dates_ordered(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError(f"{self.service_id}: end_date precedes start_date")
        return self

    @property
    def weekday_flags(self) -> tuple[bool, ...]:
        return (
            self.monday,
            self.tuesday,
            self.wednesday,
            self.thursday,
            self.friday,
            self.saturday,
            self.sunday,
        )

    @property
    def runs_on_some_day(self) -> bool:
        return any(self.weekday_flags) or bool(self.added_dates)

    def covers(self, day: dt.date) -> bool:
        if day in self.removed_dates:
            return False
        if day in self.added_dates:
            return True
        if not (self.start_date <= day <= self.end_date):
            return False
        return self.weekday_flags[day.weekday()]


class TripDeparture(BaseModel):
    """One scheduled run: a pattern leaving its origin at a published time."""

    model_config = ConfigDict(extra="forbid")

    trip_id: str
    pattern_id: str
    service_id: str
    departure: str
    """``HH:MM:SS`` from the origin stop. May exceed 24h for after-midnight runs."""

    source_id: str
    """The authoritative source for this departure time."""

    notes: str | None = None

    @field_validator("departure")
    @classmethod
    def _valid_gtfs_time(cls, value: str) -> str:
        if not re.match(r"^\d{1,3}:[0-5]\d:[0-5]\d$", value):
            raise ValueError(f"departure must be H:MM:SS or HH:MM:SS, got {value!r}")
        return value

    @property
    def departure_seconds(self) -> int:
        hours, minutes, seconds = (int(part) for part in self.departure.split(":"))
        return hours * 3600 + minutes * 60 + seconds


class Shape(BaseModel):
    """Route geometry as an ordered list of ``(lat, lon)`` points."""

    model_config = ConfigDict(extra="forbid")

    shape_id: str
    points: list[tuple[float, float]] = Field(min_length=2)
    source_id: str
    confidence: Confidence
    notes: str | None = None

    @property
    def length_m(self) -> float:
        return sum(
            haversine_m(a[0], a[1], b[0], b[1])
            for a, b in zip(self.points, self.points[1:], strict=False)
        )

    def max_segment_m(self) -> float:
        return max(
            (
                haversine_m(a[0], a[1], b[0], b[1])
                for a, b in zip(self.points, self.points[1:], strict=False)
            ),
            default=0.0,
        )

    def distance_to_point_m(self, latitude: float, longitude: float) -> float:
        """Closest approach of the polyline to a point, measured at the vertices.

        Vertex sampling is enough for QA because generated shapes are densified
        from road geometry; a shape that only passes near a stop mid-segment
        would be too coarse to publish anyway.
        """
        return min(haversine_m(latitude, longitude, lat, lon) for lat, lon in self.points)


class FeedInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feed_publisher_name: str
    feed_publisher_url: str
    feed_lang: str = "es"
    feed_version: str
    feed_start_date: dt.date | None = None
    feed_end_date: dt.date | None = None
    feed_contact_email: str | None = None
    feed_contact_url: str | None = None


class Network(BaseModel):
    """The complete canonical dataset."""

    model_config = ConfigDict(extra="forbid")

    agency: Agency
    feed_info: FeedInfo
    stops: list[Stop] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)
    patterns: list[Pattern] = Field(default_factory=list)
    services: list[ServicePeriod] = Field(default_factory=list)
    trips: list[TripDeparture] = Field(default_factory=list)
    shapes: list[Shape] = Field(default_factory=list)

    @property
    def stops_by_id(self) -> dict[str, Stop]:
        return {stop.internal_stop_id: stop for stop in self.stops}

    @property
    def routes_by_id(self) -> dict[str, Route]:
        return {route.route_id: route for route in self.routes}

    @property
    def patterns_by_id(self) -> dict[str, Pattern]:
        return {pattern.pattern_id: pattern for pattern in self.patterns}

    @property
    def services_by_id(self) -> dict[str, ServicePeriod]:
        return {service.service_id: service for service in self.services}

    @property
    def shapes_by_id(self) -> dict[str, Shape]:
        return {shape.shape_id: shape for shape in self.shapes}

    def publishable_patterns(self) -> list[Pattern]:
        publishable_routes = {
            route.route_id
            for route in self.routes
            if route.status is PublicationStatus.PUBLISHABLE
        }
        return [
            pattern
            for pattern in self.patterns
            if pattern.is_publishable and pattern.route_id in publishable_routes
        ]

    def publishable_trips(self) -> list[TripDeparture]:
        allowed = {pattern.pattern_id for pattern in self.publishable_patterns()}
        return [trip for trip in self.trips if trip.pattern_id in allowed]
