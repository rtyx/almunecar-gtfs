"""Reading and writing ``data/canonical``.

Canonical files are *generated* by reconciliation but *committed* to the
repository, so that every change to what we believe the network is shows up as a
reviewable diff. Serialisation is therefore deterministic: stable ordering,
stable key order, no timestamps.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from almunecar_gtfs.models import (
    Agency,
    FeedInfo,
    Network,
    Pattern,
    Route,
    ServicePeriod,
    Shape,
    Stop,
    TripDeparture,
)

AGENCY_FILE = "agency.yaml"
ROUTES_FILE = "routes.yaml"
STOPS_FILE = "stops.geojson"
PATTERNS_FILE = "patterns.yaml"
SCHEDULES_FILE = "schedules.yaml"
SERVICES_FILE = "services.yaml"
SHAPES_FILE = "shapes.geojson"


def _write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


def _read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return yaml.safe_load(path.read_text(encoding="utf-8")) or default


def _write_geojson(path: Path, features: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "FeatureCollection", "features": features}
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _read_geojson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("features", [])


def _round_coord(value: float) -> float:
    """Six decimal places: ~0.1 m, well beyond what any of our sources justify."""
    return round(value, 6)


# -- stops ---------------------------------------------------------------


def stop_to_feature(stop: Stop) -> dict[str, Any]:
    properties = stop.model_dump(mode="json", exclude_none=True)
    properties.pop("latitude")
    properties.pop("longitude")
    return {
        "type": "Feature",
        "id": stop.internal_stop_id,
        "geometry": {
            "type": "Point",
            "coordinates": [_round_coord(stop.longitude), _round_coord(stop.latitude)],
        },
        "properties": properties,
    }


def feature_to_stop(feature: dict[str, Any]) -> Stop:
    longitude, latitude = feature["geometry"]["coordinates"][:2]
    return Stop.model_validate(
        {**feature["properties"], "latitude": latitude, "longitude": longitude}
    )


def write_stops(path: Path, stops: Sequence[Stop]) -> None:
    ordered = sorted(stops, key=lambda s: s.internal_stop_id)
    _write_geojson(path, [stop_to_feature(stop) for stop in ordered])


def read_stops(path: Path) -> list[Stop]:
    return [feature_to_stop(feature) for feature in _read_geojson(path)]


# -- shapes --------------------------------------------------------------


def shape_to_feature(shape: Shape) -> dict[str, Any]:
    properties = shape.model_dump(mode="json", exclude_none=True)
    properties.pop("points")
    return {
        "type": "Feature",
        "id": shape.shape_id,
        "geometry": {
            "type": "LineString",
            "coordinates": [[_round_coord(lon), _round_coord(lat)] for lat, lon in shape.points],
        },
        "properties": properties,
    }


def feature_to_shape(feature: dict[str, Any]) -> Shape:
    points = [(lat, lon) for lon, lat in feature["geometry"]["coordinates"]]
    return Shape.model_validate({**feature["properties"], "points": points})


def write_shapes(path: Path, shapes: Sequence[Shape]) -> None:
    ordered = sorted(shapes, key=lambda s: s.shape_id)
    _write_geojson(path, [shape_to_feature(shape) for shape in ordered])


def read_shapes(path: Path) -> list[Shape]:
    return [feature_to_shape(feature) for feature in _read_geojson(path)]


# -- whole network -------------------------------------------------------


def write_network(canonical_dir: Path, network: Network) -> None:
    canonical_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(
        canonical_dir / AGENCY_FILE,
        {
            "agency": network.agency.model_dump(mode="json", exclude_none=True),
            "feed_info": network.feed_info.model_dump(mode="json", exclude_none=True),
        },
    )
    _write_yaml(
        canonical_dir / ROUTES_FILE,
        [
            route.model_dump(mode="json", exclude_none=True)
            for route in sorted(network.routes, key=lambda r: r.route_id)
        ],
    )
    _write_yaml(
        canonical_dir / PATTERNS_FILE,
        [
            pattern.model_dump(mode="json", exclude_none=True)
            for pattern in sorted(network.patterns, key=lambda p: p.pattern_id)
        ],
    )
    _write_yaml(
        canonical_dir / SERVICES_FILE,
        [
            service.model_dump(mode="json", exclude_none=True)
            for service in sorted(network.services, key=lambda s: s.service_id)
        ],
    )
    _write_yaml(
        canonical_dir / SCHEDULES_FILE,
        [
            trip.model_dump(mode="json", exclude_none=True)
            for trip in sorted(network.trips, key=lambda t: (t.pattern_id, t.departure, t.trip_id))
        ],
    )
    write_stops(canonical_dir / STOPS_FILE, network.stops)
    write_shapes(canonical_dir / SHAPES_FILE, network.shapes)


def read_network(canonical_dir: Path) -> Network:
    agency_payload = _read_yaml(canonical_dir / AGENCY_FILE, {})
    if not agency_payload:
        raise FileNotFoundError(
            f"{canonical_dir / AGENCY_FILE} is missing or empty; run `almunecar-gtfs reconcile`"
        )
    return Network(
        agency=Agency.model_validate(agency_payload["agency"]),
        feed_info=FeedInfo.model_validate(agency_payload["feed_info"]),
        routes=[Route.model_validate(item) for item in _read_yaml(canonical_dir / ROUTES_FILE, [])],
        patterns=[
            Pattern.model_validate(item) for item in _read_yaml(canonical_dir / PATTERNS_FILE, [])
        ],
        services=[
            ServicePeriod.model_validate(item)
            for item in _read_yaml(canonical_dir / SERVICES_FILE, [])
        ],
        trips=[
            TripDeparture.model_validate(item)
            for item in _read_yaml(canonical_dir / SCHEDULES_FILE, [])
        ],
        stops=read_stops(canonical_dir / STOPS_FILE),
        shapes=read_shapes(canonical_dir / SHAPES_FILE),
    )
