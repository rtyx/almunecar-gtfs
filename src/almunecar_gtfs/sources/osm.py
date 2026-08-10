"""OpenStreetMap extraction via Overpass.

OSM sits low in the coordinate hierarchy but it is the one source that reliably
distinguishes the two poles of a stop pair, so it is valuable corroboration even
when it does not win.

Only ``highway=bus_stop`` and ``public_transport=platform`` count as stop
evidence. Anything else OSM happens to call by the same name is a POI.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from almunecar_gtfs.models import SERVICE_AREA_BBOX
from almunecar_gtfs.provenance import Confidence, EvidenceKind, Observation
from almunecar_gtfs.sources.base import DEFAULT_TIMEOUT, USER_AGENT

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SOURCE_ID = "osm_overpass_bus_stops"


def overpass_query(bbox: tuple[float, float, float, float] = SERVICE_AREA_BBOX) -> str:
    min_lat, min_lon, max_lat, max_lon = bbox
    area = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    return f"""
[out:json][timeout:60];
(
  node["highway"="bus_stop"]({area});
  node["public_transport"="platform"]["bus"="yes"]({area});
);
out body;
""".strip()


@dataclass(frozen=True)
class OsmStop:
    node_id: int
    name: str | None
    latitude: float
    longitude: float
    tags: dict[str, str]

    @property
    def is_verified_stop(self) -> bool:
        return (
            self.tags.get("highway") == "bus_stop"
            or self.tags.get("public_transport") == "platform"
        )


def parse_overpass(payload: dict) -> list[OsmStop]:
    stops = []
    for element in payload.get("elements", []):
        if element.get("type") != "node":
            continue
        tags = element.get("tags", {})
        stops.append(
            OsmStop(
                node_id=element["id"],
                name=tags.get("name"),
                latitude=element["lat"],
                longitude=element["lon"],
                tags=tags,
            )
        )
    return sorted(stops, key=lambda s: s.node_id)


def fetch_stops(cache_path: Path | None = None, *, force: bool = False) -> list[OsmStop]:
    if cache_path is not None and cache_path.exists() and not force:
        return parse_overpass(json.loads(cache_path.read_text(encoding="utf-8")))
    response = httpx.post(
        OVERPASS_URL,
        data={"data": overpass_query()},
        headers={"User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return parse_overpass(payload)


def to_observations(
    stops: list[OsmStop],
    stop_id_by_node: dict[int, str],
    retrieved_at: dt.date | None = None,
) -> list[Observation]:
    """Emit coordinate evidence for OSM nodes already matched to our stop ids.

    Matching is intentionally not done here. Deciding that OSM node 123 is our
    ``ALM_0007`` is a reconciliation judgement that a human makes once and
    records; a scraper guessing at it would invent stops.
    """
    retrieved_at = retrieved_at or dt.date.today()
    observations = []
    for stop in stops:
        internal_id = stop_id_by_node.get(stop.node_id)
        if internal_id is None:
            continue
        entity = f"stop:{internal_id}"
        observations.append(
            Observation(
                entity=entity,
                field="coordinate",
                value=f"{stop.latitude:.6f},{stop.longitude:.6f}",
                source_id=SOURCE_ID,
                retrieved_at=retrieved_at,
                confidence=Confidence.MEDIUM if stop.is_verified_stop else Confidence.LOW,
                evidence_kind=(
                    EvidenceKind.BUS_STOP_NODE if stop.is_verified_stop else EvidenceKind.POI
                ),
                source_url=f"https://www.openstreetmap.org/node/{stop.node_id}",
                notes=f"tags: {', '.join(f'{k}={v}' for k, v in sorted(stop.tags.items()))}",
            )
        )
        observations.append(
            Observation(
                entity=entity,
                field="osm_node_id",
                value=str(stop.node_id),
                source_id=SOURCE_ID,
                retrieved_at=retrieved_at,
                confidence=Confidence.HIGH,
            )
        )
    return observations
