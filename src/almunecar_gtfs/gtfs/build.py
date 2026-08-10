"""Deterministic GTFS Schedule generation from the canonical dataset.

Only publishable entities reach the feed. A pattern with unknown intermediate
timings is dropped with a loud message rather than filled in with invented
numbers, and the same canonical input always produces a byte-identical zip.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from collections.abc import Sequence
from pathlib import Path

from almunecar_gtfs.models import (
    Network,
    Pattern,
    PublicationStatus,
    Shape,
    Stop,
    haversine_m,
)

#: Fixed member timestamp so repeated builds are byte-identical.
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

GTFS_FILES: tuple[str, ...] = (
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "shapes.txt",
    "feed_info.txt",
)

REQUIRED_GTFS_FILES: frozenset[str] = frozenset(
    {
        "agency.txt",
        "stops.txt",
        "routes.txt",
        "trips.txt",
        "stop_times.txt",
        "calendar.txt",
    }
)


class BuildError(Exception):
    """Raised when the canonical dataset cannot produce a coherent feed."""


def format_time(seconds: int) -> str:
    """GTFS time. Hours may exceed 24 for trips that run past midnight."""
    if seconds < 0:
        raise BuildError(f"negative stop time: {seconds}")
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_date(day: dt.date) -> str:
    return day.strftime("%Y%m%d")


def _rows_to_csv(header: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return buffer.getvalue()


def _bool(value: bool) -> int:
    return 1 if value else 0


# -- individual files ----------------------------------------------------


def build_agency(network: Network) -> str:
    agency = network.agency
    header = (
        "agency_id",
        "agency_name",
        "agency_url",
        "agency_timezone",
        "agency_lang",
        "agency_phone",
    )
    row = (
        agency.agency_id,
        agency.agency_name,
        agency.agency_url,
        agency.agency_timezone,
        agency.agency_lang,
        agency.agency_phone,
    )
    return _rows_to_csv(header, [row])


def _used_stops(network: Network) -> list[Stop]:
    """Only stops actually served by a published trip reach stops.txt."""
    used: set[str] = set()
    published_patterns = {p.pattern_id for p in network.publishable_patterns()}
    for trip in network.publishable_trips():
        pattern = network.patterns_by_id[trip.pattern_id]
        if pattern.pattern_id in published_patterns:
            used.update(pattern.stop_ids)
    return sorted(
        (stop for stop in network.stops if stop.internal_stop_id in used),
        key=lambda s: s.internal_stop_id,
    )


def build_stops(network: Network) -> str:
    header = (
        "stop_id",
        "stop_name",
        "stop_lat",
        "stop_lon",
        "location_type",
        "stop_desc",
        "zone_id",
    )
    rows = [
        (
            stop.internal_stop_id,
            stop.name,
            f"{stop.latitude:.6f}",
            f"{stop.longitude:.6f}",
            0,
            stop.direction_hint,
            stop.municipality,
        )
        for stop in _used_stops(network)
    ]
    return _rows_to_csv(header, rows)


def build_routes(network: Network) -> str:
    header = (
        "route_id",
        "agency_id",
        "route_short_name",
        "route_long_name",
        "route_desc",
        "route_type",
        "route_color",
        "route_text_color",
    )
    published_route_ids = {p.route_id for p in network.publishable_patterns()}
    rows = [
        (
            route.route_id,
            network.agency.agency_id,
            route.route_short_name,
            route.route_long_name,
            route.route_desc,
            route.route_type,
            route.route_color,
            route.route_text_color,
        )
        for route in sorted(network.routes, key=lambda r: r.route_id)
        if route.route_id in published_route_ids
        and route.status is PublicationStatus.PUBLISHABLE
    ]
    return _rows_to_csv(header, rows)


def build_trips(network: Network) -> str:
    header = (
        "route_id",
        "service_id",
        "trip_id",
        "trip_headsign",
        "direction_id",
        "shape_id",
    )
    rows = []
    for trip in sorted(network.publishable_trips(), key=lambda t: t.trip_id):
        pattern = network.patterns_by_id[trip.pattern_id]
        rows.append(
            (
                pattern.route_id,
                trip.service_id,
                trip.trip_id,
                pattern.headsign,
                pattern.direction_id,
                pattern.shape_id,
            )
        )
    return _rows_to_csv(header, rows)


def _shape_distances(shape: Shape | None, pattern: Pattern, network: Network) -> list[float | None]:
    """Distance along the shape at each stop, used for `shape_dist_traveled`.

    Matching is greedy and forward-only: each stop takes the nearest remaining
    vertex at or after the previous stop's vertex, so a pattern that passes the
    same road twice cannot snap backwards.
    """
    if shape is None:
        return [None] * len(pattern.stops)

    cumulative = [0.0]
    for first, second in zip(shape.points, shape.points[1:], strict=False):
        cumulative.append(cumulative[-1] + haversine_m(first[0], first[1], second[0], second[1]))

    distances: list[float | None] = []
    cursor = 0
    for stop_id in pattern.stop_ids:
        stop = network.stops_by_id.get(stop_id)
        if stop is None:
            distances.append(None)
            continue
        best_index = cursor
        best_distance = float("inf")
        for index in range(cursor, len(shape.points)):
            latitude, longitude = shape.points[index]
            candidate = haversine_m(stop.latitude, stop.longitude, latitude, longitude)
            if candidate < best_distance:
                best_distance = candidate
                best_index = index
        cursor = best_index
        distances.append(round(cumulative[best_index], 1))
    return distances


def build_stop_times(network: Network) -> str:
    header = (
        "trip_id",
        "arrival_time",
        "departure_time",
        "stop_id",
        "stop_sequence",
        "stop_headsign",
        "pickup_type",
        "drop_off_type",
        "shape_dist_traveled",
        "timepoint",
    )
    rows = []
    for trip in sorted(network.publishable_trips(), key=lambda t: t.trip_id):
        pattern = network.patterns_by_id[trip.pattern_id]
        shape = network.shapes_by_id.get(pattern.shape_id or "")
        distances = _shape_distances(shape, pattern, network)
        origin = trip.departure_seconds
        for sequence, (pattern_stop, distance) in enumerate(
            zip(pattern.stops, distances, strict=True), start=1
        ):
            if pattern_stop.offset_seconds is None:
                raise BuildError(
                    f"{pattern.pattern_id}: stop {pattern_stop.stop_id} has no offset; "
                    f"the pattern should not be publishable"
                )
            moment = format_time(origin + pattern_stop.offset_seconds)
            boarding = 3 if pattern_stop.request_stop else 0
            rows.append(
                (
                    trip.trip_id,
                    moment,
                    moment,
                    pattern_stop.stop_id,
                    sequence,
                    pattern_stop.stop_headsign,
                    boarding,
                    boarding,
                    distance,
                    _bool(pattern_stop.is_timepoint),
                )
            )
    return _rows_to_csv(header, rows)


def _used_service_ids(network: Network) -> set[str]:
    return {trip.service_id for trip in network.publishable_trips()}


def build_calendar(network: Network) -> str:
    header = (
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    )
    used = _used_service_ids(network)
    rows = [
        (
            service.service_id,
            *(_bool(flag) for flag in service.weekday_flags),
            format_date(service.start_date),
            format_date(service.end_date),
        )
        for service in sorted(network.services, key=lambda s: s.service_id)
        if service.service_id in used
    ]
    return _rows_to_csv(header, rows)


def build_calendar_dates(network: Network) -> str:
    header = ("service_id", "date", "exception_type")
    used = _used_service_ids(network)
    rows = []
    for service in sorted(network.services, key=lambda s: s.service_id):
        if service.service_id not in used:
            continue
        for day in sorted(service.added_dates):
            rows.append((service.service_id, format_date(day), 1))
        for day in sorted(service.removed_dates):
            rows.append((service.service_id, format_date(day), 2))
    return _rows_to_csv(header, rows)


def build_shapes(network: Network) -> str:
    header = (
        "shape_id",
        "shape_pt_lat",
        "shape_pt_lon",
        "shape_pt_sequence",
        "shape_dist_traveled",
    )
    used = {p.shape_id for p in network.publishable_patterns() if p.shape_id}
    rows = []
    for shape in sorted(network.shapes, key=lambda s: s.shape_id):
        if shape.shape_id not in used:
            continue
        travelled = 0.0
        previous: tuple[float, float] | None = None
        for sequence, (latitude, longitude) in enumerate(shape.points, start=1):
            if previous is not None:
                travelled += haversine_m(previous[0], previous[1], latitude, longitude)
            previous = (latitude, longitude)
            rows.append(
                (
                    shape.shape_id,
                    f"{latitude:.6f}",
                    f"{longitude:.6f}",
                    sequence,
                    round(travelled, 1),
                )
            )
    return _rows_to_csv(header, rows)


def build_feed_info(network: Network) -> str:
    info = network.feed_info
    header = (
        "feed_publisher_name",
        "feed_publisher_url",
        "feed_lang",
        "feed_start_date",
        "feed_end_date",
        "feed_version",
        "feed_contact_email",
        "feed_contact_url",
    )
    row = (
        info.feed_publisher_name,
        info.feed_publisher_url,
        info.feed_lang,
        format_date(info.feed_start_date) if info.feed_start_date else None,
        format_date(info.feed_end_date) if info.feed_end_date else None,
        info.feed_version,
        info.feed_contact_email,
        info.feed_contact_url,
    )
    return _rows_to_csv(header, [row])


# -- assembly ------------------------------------------------------------


def build_feed(network: Network) -> dict[str, str]:
    """Render every GTFS file as text, keyed by filename."""
    if not network.publishable_trips():
        raise BuildError(
            "no publishable trips; refusing to build an empty feed. Check pattern "
            "timings and publication status."
        )
    return {
        "agency.txt": build_agency(network),
        "stops.txt": build_stops(network),
        "routes.txt": build_routes(network),
        "trips.txt": build_trips(network),
        "stop_times.txt": build_stop_times(network),
        "calendar.txt": build_calendar(network),
        "calendar_dates.txt": build_calendar_dates(network),
        "shapes.txt": build_shapes(network),
        "feed_info.txt": build_feed_info(network),
    }


def write_feed(output_dir: Path, feed: dict[str, str]) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in GTFS_FILES:
        content = feed.get(name)
        if content is None:
            continue
        path = output_dir / name
        path.write_text(content, encoding="utf-8", newline="")
        written.append(path)
    return written


def write_zip(zip_path: Path, feed: dict[str, str]) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in GTFS_FILES:
            content = feed.get(name)
            if content is None:
                continue
            info = zipfile.ZipInfo(filename=name, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content.encode("utf-8"))
    return zip_path
