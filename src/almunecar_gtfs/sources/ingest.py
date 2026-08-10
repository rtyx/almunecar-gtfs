"""Turn cached sources into ``data/evidence``.

This is the only writer of ``sources.yaml`` and ``observations.csv``. It reads
the operator transcriptions in :mod:`~almunecar_gtfs.sources.official`, the
cached Overpass responses, and the committed stop registry, and emits
observations. It never writes canonical data or GTFS.

The stop registry (``data/evidence/stop_registry.yaml``) is the one hand-owned
link in the chain: deciding that OSM node 4266754568 is our ``ALM_0001`` is a
human judgement. It is generated once from the OSM route relations and then
maintained by hand; re-running ingestion never renumbers an existing stop.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from almunecar_gtfs.provenance import (
    Confidence,
    EvidenceKind,
    Observation,
    Source,
    SourceType,
    dump_observations,
    dump_sources,
    load_sources,
)
from almunecar_gtfs.sources import images as images_mod
from almunecar_gtfs.sources import official
from almunecar_gtfs.sources.base import fetch

#: The Overpass extract is committed under ``data/evidence`` rather than left in
#: the git-ignored cache: ingestion has to be reproducible offline, and OSM data
#: is ODbL-licensed open data we may redistribute with attribution.
OSM_RELATIONS_FILE = "osm/relations.json"
STOP_REGISTRY_FILE = "stop_registry.yaml"

OSM_SOURCE_ID = "osm_route_relations"
IMG_BASE = "https://urbanosalmunecar.es/wp-content/uploads"
OSM_ATTRIBUTION = "© OpenStreetMap contributors, ODbL"

#: OSM route relations, in the order stop ids were first assigned.
OSM_RELATIONS: dict[int, dict[str, str]] = {
    11185550: {"route_id": "ALM_1", "pattern_id": "ALM_1_CIRC", "headsign": "Circular"},
    18501805: {"route_id": "ALM_2A", "pattern_id": "ALM_2A_CIRC", "headsign": "La Herradura"},
    18496909: {
        "route_id": "ALM_2B",
        "pattern_id": "ALM_2B_CIRC_SUMMER",
        "headsign": "La Herradura – Punta de la Mona",
    },
    11186061: {"route_id": "ALM_3A", "pattern_id": "ALM_3A_CIRC", "headsign": "Velilla – Taramay"},
    18501914: {
        "route_id": "ALM_TORRECUEVAS",
        "pattern_id": "ALM_TORRECUEVAS_CIRC",
        "headsign": "Torrecuevas",
    },
}

#: Marina del Este (Puerto Deportivo). The operator's 2B diagram marks this stop
#: with an asterisk and the winter page explains: "Esta parada no se realiza en
#: el horario de invierno."
MARINA_DEL_ESTE_OSM_NODE = 4167568437

#: The Torrecuevas relation's platform members are not in travel order — it puts
#: Cortijo Cahicillos, the far apex, between two stops beside the town. The
#: operator's own route diagram states the order, and the operator outranks OSM
#: for stop sequences, so this maps each diagram call to the stop we hold for it.
#:
#: ``None`` means the operator names a call that is not mapped in OSM at all.
#: Those are listed rather than dropped silently: they are exactly the survey
#: work needed to complete the line.
TORRECUEVAS_DIAGRAM_ORDER: tuple[tuple[str, str | None], ...] = (
    ("PLAZA DE LA CARRERA", "ALM_0001"),
    ("SAN SEBASTIAN 1", "ALM_0072"),
    ("SAN SEBASTIAN 2", "ALM_0069"),
    ("LADERAS DE CASTELAR", "ALM_0060"),
    ("CEMENTERIO", None),
    ("PEÑUELAS", "ALM_0065"),
    ("VTA LUCIANO 1", "ALM_0061"),
    ("VTA LUCIANO 2", None),
    ("TORRECUEVAS", "ALM_0062"),
    ("ARCOS TORRECUEVAS", "ALM_0063"),
    ("EUCALIPTO", None),
    ("CAHICILLOS 1", "ALM_0073"),
    ("CAHICILLOS 2", None),
    ("CAHICILLOS 1 R", None),
    ("EUCALIPTO R", None),
    ("ARCOS TORRECUEVAS R", "ALM_0064"),
    ("TORRECUEVAS R", "ALM_0074"),
    ("VTA LUCIANO 2 R", "ALM_0066"),
    ("VTA LUCIANO 1 R", None),
    ("PEÑUELAS R", "ALM_0067"),
    ("CEMENTERIO R", None),
    ("LADERAS DE CASTELAR R", "ALM_0068"),
    ("SAN SEBASTIAN 2 R", "ALM_0070"),
    ("SAN SEBASTIAN 1 R", "ALM_0071"),
    ("PLAZA DE LA CARRERA R", "ALM_0001"),
)

SEASONS: dict[str, tuple[dt.date, dt.date]] = {
    # Only the periods the operator currently documents. Future seasons are not
    # assumed to repeat; they are added when the operator publishes them.
    "summer": (dt.date(2026, 7, 1), dt.date(2026, 9, 15)),
    "winter": (dt.date(2026, 9, 16), dt.date(2027, 6, 30)),
}

SERVICE_WEEKDAYS: dict[str, str] = {
    "MONSAT": "mon;tue;wed;thu;fri;sat",
    "MONFRI": "mon;tue;wed;thu;fri",
    "SAT": "sat",
    "SUNHOL": "sun",
    "MONSAT_PUERTO": "mon;tue;wed;thu;fri;sat",
    "SUNHOL_PUERTO": "sun",
}

ROUTES: dict[str, dict[str, object]] = {
    "ALM_1": {
        "short": "1",
        "long": "Circular",
        "seasons": "summer;winter",
        "status": "not_publishable",
        "desc": (
            "Circular. Routing is temporarily diverted via calle Guadix while Paseo "
            "del Altillo is closed for roadworks from 13 April 2026 for about ten "
            "months; the available geometry does not reflect the diversion."
        ),
    },
    "ALM_2A": {"short": "2A", "long": "Almuñécar – La Herradura", "seasons": "summer;winter"},
    "ALM_2B": {
        "short": "2B",
        "long": "Almuñécar – La Herradura – Punta de la Mona",
        "seasons": "summer;winter",
    },
    "ALM_3A": {"short": "3A", "long": "Velilla – Taramay", "seasons": "summer;winter"},
    "ALM_3B": {
        "short": "3B",
        "long": "Velilla",
        "seasons": "summer",
        "status": "not_publishable",
        "desc": (
            "Summer only. No machine-readable stop sequence or coordinates are "
            "available for this line; the operator diagram names stops that are not "
            "mapped, and the Monday-to-Saturday timetable is published as a frequency."
        ),
    },
    "ALM_3C": {
        "short": "3C",
        "long": "Taramay",
        "seasons": "summer",
        "status": "not_publishable",
        "desc": "Summer only. No machine-readable stop sequence or coordinates available.",
    },
    "ALM_TORRECUEVAS": {
        "short": None,  # disputed; recorded as competing observations
        "long": "Torrecuevas",
        "seasons": "summer;winter",
        "status": "not_publishable",
        "desc": "Line number disputed between the operator's own summer and winter pages.",
    },
}


@dataclass(frozen=True)
class RegisteredStop:
    internal_stop_id: str
    osm_node_id: int
    name: str
    latitude: float
    longitude: float
    municipality: str
    verified_bus_stop: bool


def _load_relations(evidence_dir: Path) -> tuple[dict, dict, dict]:
    payload = json.loads((evidence_dir / OSM_RELATIONS_FILE).read_text(encoding="utf-8"))
    elements = payload["elements"]
    relations = {e["id"]: e for e in elements if e["type"] == "relation"}
    nodes = {e["id"]: e for e in elements if e["type"] == "node"}
    ways = {e["id"]: e for e in elements if e["type"] == "way"}
    return relations, nodes, ways


def _platform_members(relation: dict) -> list[int]:
    return [
        member["ref"]
        for member in relation["members"]
        if member["type"] == "node" and member["role"].startswith("platform")
    ]


def _municipality(name: str, latitude: float, longitude: float) -> str:
    """La Herradura is a pedanía of Almuñécar but signs itself separately."""
    if longitude < -3.725:
        return "La Herradura"
    return "Almuñécar"


def build_stop_registry(evidence_dir: Path) -> list[RegisteredStop]:
    relations, nodes, _ = _load_relations(evidence_dir)
    ordered: list[int] = []
    for relation_id in OSM_RELATIONS:
        for node_id in _platform_members(relations[relation_id]):
            if node_id not in ordered:
                ordered.append(node_id)

    registry = []
    for index, node_id in enumerate(ordered, start=1):
        node = nodes[node_id]
        tags = node.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        registry.append(
            RegisteredStop(
                internal_stop_id=f"ALM_{index:04d}",
                osm_node_id=node_id,
                name=name,
                latitude=round(node["lat"], 6),
                longitude=round(node["lon"], 6),
                municipality=_municipality(name, node["lat"], node["lon"]),
                verified_bus_stop=(
                    tags.get("highway") == "bus_stop"
                    or tags.get("public_transport") == "platform"
                ),
            )
        )
    return registry


def load_or_create_registry(evidence_dir: Path) -> list[RegisteredStop]:
    path = evidence_dir / STOP_REGISTRY_FILE
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        return [RegisteredStop(**item) for item in raw]

    registry = build_stop_registry(evidence_dir)
    path.write_text(
        "# Physical stop registry. Hand-owned: the link between an OSM node and an\n"
        "# ALM id is a human judgement, and ids are never renumbered once assigned.\n"
        "# Generated once from the OSM route relations; edit in place afterwards.\n"
        + yaml.safe_dump(
            [stop.__dict__ for stop in registry], allow_unicode=True, sort_keys=False
        ),
        encoding="utf-8",
    )
    return registry


def _sources(operator_hashes: dict[str, str], today: dt.date) -> list[Source]:
    sources = [
        Source(
            source_id=page.source_id,
            source_type=SourceType.OFFICIAL,
            source_url=page.url,
            title=page.title,
            retrieved_at=today,
            content_sha256=operator_hashes.get(page.source_id),
            notes=(
                f"Operator page; sitemap lastmod {page.lastmod}. Covers: {page.covers}. "
                f"Timetables are published as images and were transcribed by hand."
            ),
        )
        for page in official.PAGES
    ]
    sources.append(
        Source(
            source_id=OSM_SOURCE_ID,
            source_type=SourceType.OSM,
            source_url="https://overpass-api.de/api/interpreter",
            title="OpenStreetMap bus route relations for Grupo Fajardo, via Overpass",
            retrieved_at=today,
            license=OSM_ATTRIBUTION,
            notes=(
                "Relations 11185550, 11186061, 18496909, 18501805, 18501914. "
                "Supplies stop coordinates, ordered stop sequences and route geometry. "
                "Ranks below the operator for anything the operator states."
            ),
        )
    )
    return sources


def _route_observations(today: dt.date) -> list[Observation]:
    rows: list[Observation] = []
    for route_id, spec in ROUTES.items():
        entity = f"route:{route_id}"
        if spec["short"] is not None:
            rows.append(
                Observation(
                    entity=entity,
                    field="route_short_name",
                    value=str(spec["short"]),
                    source_id="official_index",
                    retrieved_at=today,
                    confidence=Confidence.CONFIRMED,
                    evidence_kind=EvidenceKind.NARRATIVE,
                )
            )
        rows.append(
            Observation(
                entity=entity,
                field="route_long_name",
                value=str(spec["long"]),
                source_id="official_index",
                retrieved_at=today,
                confidence=Confidence.CONFIRMED,
                evidence_kind=EvidenceKind.NARRATIVE,
            )
        )
        rows.append(
            Observation(
                entity=entity,
                field="seasons",
                value=str(spec["seasons"]),
                source_id="official_index",
                retrieved_at=today,
                confidence=Confidence.HIGH,
            )
        )
        if spec.get("status"):
            rows.append(
                Observation(
                    entity=entity,
                    field="status",
                    value=str(spec["status"]),
                    source_id="official_index",
                    retrieved_at=today,
                    confidence=Confidence.CONFIRMED,
                    notes=str(spec.get("desc", "")) or None,
                )
            )
        if spec.get("desc"):
            rows.append(
                Observation(
                    entity=entity,
                    field="route_desc",
                    value=str(spec["desc"]),
                    source_id="official_index",
                    retrieved_at=today,
                    confidence=Confidence.HIGH,
                )
            )

    # The disputed Torrecuevas number: both operator claims, recorded side by
    # side so reconciliation raises a conflict instead of picking one.
    rows += [
        Observation(
            entity="route:ALM_TORRECUEVAS",
            field="route_short_name",
            value="4",
            source_id="official_torrecuevas_summer",
            retrieved_at=today,
            confidence=Confidence.HIGH,
            evidence_kind=EvidenceKind.NARRATIVE,
            source_url=official.PAGES_BY_ID["official_torrecuevas_summer"].url,
            notes=(
                "Page body heading reads 'LINEA 4 TORRECUEVAS'. The same page's "
                "validity sentence wrongly says 'horario de invierno' for 1 July to "
                "15 September, so the page is not carefully maintained."
            ),
        ),
        Observation(
            entity="route:ALM_TORRECUEVAS",
            field="route_short_name",
            value="5",
            source_id="official_torrecuevas_winter",
            retrieved_at=today,
            confidence=Confidence.HIGH,
            evidence_kind=EvidenceKind.NARRATIVE,
            source_url=official.PAGES_BY_ID["official_torrecuevas_winter"].url,
            notes=(
                "Page title reads 'Línea 5 Torrecuevas invierno' and the URL slug "
                "contains 'linea-5'. Same sitemap lastmod as the summer page "
                "(2026-05-14), so neither can be dismissed as simply older."
            ),
        ),
        Observation(
            entity="route:ALM_TORRECUEVAS",
            field="route_short_name",
            value="5",
            source_id=OSM_SOURCE_ID,
            retrieved_at=today,
            confidence=Confidence.MEDIUM,
            source_url="https://www.openstreetmap.org/relation/18501914",
            notes="OSM relation ref='Línea 5', operator='Grupo Fajardo'.",
        ),
    ]
    return rows


def _stop_observations(registry: list[RegisteredStop], today: dt.date) -> list[Observation]:
    rows: list[Observation] = []
    for stop in registry:
        entity = f"stop:{stop.internal_stop_id}"
        rows += [
            Observation(
                entity=entity,
                field="name",
                value=stop.name,
                source_id=OSM_SOURCE_ID,
                retrieved_at=today,
                confidence=Confidence.MEDIUM,
                source_url=f"https://www.openstreetmap.org/node/{stop.osm_node_id}",
                notes="OSM name; the operator's diagrams use different wording.",
            ),
            Observation(
                entity=entity,
                field="coordinate",
                value=f"{stop.latitude:.6f},{stop.longitude:.6f}",
                source_id=OSM_SOURCE_ID,
                retrieved_at=today,
                confidence=Confidence.MEDIUM if stop.verified_bus_stop else Confidence.LOW,
                evidence_kind=(
                    EvidenceKind.BUS_STOP_NODE if stop.verified_bus_stop else EvidenceKind.POI
                ),
                source_url=f"https://www.openstreetmap.org/node/{stop.osm_node_id}",
            ),
            Observation(
                entity=entity,
                field="osm_node_id",
                value=str(stop.osm_node_id),
                source_id=OSM_SOURCE_ID,
                retrieved_at=today,
                confidence=Confidence.HIGH,
            ),
            Observation(
                entity=entity,
                field="municipality",
                value=stop.municipality,
                source_id=OSM_SOURCE_ID,
                retrieved_at=today,
                confidence=Confidence.MEDIUM,
                derivation="Assigned from longitude: west of -3.725 is La Herradura.",
            ),
        ]
    return rows


def _pattern_observations(
    evidence_dir: Path, registry: list[RegisteredStop], today: dt.date
) -> list[Observation]:
    relations, _, _ = _load_relations(evidence_dir)
    by_node = {stop.osm_node_id: stop.internal_stop_id for stop in registry}
    rows: list[Observation] = []

    for relation_id, spec in OSM_RELATIONS.items():
        relation = relations[relation_id]
        sequence: list[str] = []
        for node_id in _platform_members(relation):
            stop_id = by_node.get(node_id)
            if stop_id is None:
                continue
            if sequence and sequence[-1] == stop_id:
                continue  # the relation repeats the terminus member
            sequence.append(stop_id)
        if len(sequence) < 2:
            continue

        entity = f"pattern:{spec['pattern_id']}"
        url = f"https://www.openstreetmap.org/relation/{relation_id}"
        season = "summer" if spec["pattern_id"].endswith("_SUMMER") else "all_year"
        rows += [
            Observation(
                entity=entity, field="route_id", value=spec["route_id"],
                source_id=OSM_SOURCE_ID, retrieved_at=today,
                confidence=Confidence.HIGH, source_url=url,
            ),
            Observation(
                entity=entity, field="direction_id", value="0",
                source_id=OSM_SOURCE_ID, retrieved_at=today,
                confidence=Confidence.HIGH,
                notes="roundtrip=yes: one circular direction, not an out-and-back pair.",
            ),
            Observation(
                entity=entity, field="season", value=season,
                source_id=OSM_SOURCE_ID, retrieved_at=today, confidence=Confidence.MEDIUM,
            ),
            Observation(
                entity=entity, field="headsign", value=spec["headsign"],
                source_id="official_index", retrieved_at=today, confidence=Confidence.HIGH,
            ),
            Observation(
                entity=entity, field="stop_sequence", value=";".join(sequence),
                source_id=OSM_SOURCE_ID, retrieved_at=today,
                confidence=Confidence.MEDIUM, evidence_kind=EvidenceKind.BUS_STOP_NODE,
                source_url=url,
                notes=(
                    f"{len(sequence)} stops from the relation's platform members in order. "
                    f"The operator's own diagram is transcribed separately for comparison."
                ),
            ),
            Observation(
                entity=entity, field="shape_id", value=spec["pattern_id"],
                source_id=OSM_SOURCE_ID, retrieved_at=today, confidence=Confidence.HIGH,
            ),
        ]

        # Torrecuevas: override OSM's scrambled order with the operator's.
        if spec["pattern_id"] == "ALM_TORRECUEVAS_CIRC":
            ordered = [sid for _, sid in TORRECUEVAS_DIAGRAM_ORDER if sid]
            unmapped = [name for name, sid in TORRECUEVAS_DIAGRAM_ORDER if sid is None]
            rows.append(
                Observation(
                    entity=entity,
                    field="stop_sequence",
                    value=";".join(ordered),
                    source_id="official_torrecuevas_summer",
                    retrieved_at=today,
                    confidence=Confidence.HIGH,
                    evidence_kind=EvidenceKind.NARRATIVE,
                    source_url=f"{IMG_BASE}/2022/05/image-9.png",
                    derivation=(
                        "Order taken from the operator's route diagram; each diagram call "
                        "matched by name and position to the stop we hold for it. OSM's "
                        "relation lists the same platforms but not in travel order."
                    ),
                    derived_from=f"official_torrecuevas_summer;{OSM_SOURCE_ID}",
                    notes=(
                        f"The diagram names {len(TORRECUEVAS_DIAGRAM_ORDER)} calls; "
                        f"{len(unmapped)} have no mapped stop and are omitted here: "
                        + ", ".join(unmapped)
                    ),
                )
            )

        # Winter 2B: the same sequence without Marina del Este, which the
        # operator's winter page states is not served.
        if spec["pattern_id"] == "ALM_2B_CIRC_SUMMER":
            marina = by_node.get(MARINA_DEL_ESTE_OSM_NODE)
            winter_sequence = [s for s in sequence if s != marina]
            winter_entity = "pattern:ALM_2B_CIRC_WINTER"
            rows += [
                Observation(
                    entity=winter_entity, field="route_id", value="ALM_2B",
                    source_id="official_l2_winter", retrieved_at=today,
                    confidence=Confidence.HIGH,
                ),
                Observation(
                    entity=winter_entity, field="direction_id", value="0",
                    source_id="official_l2_winter", retrieved_at=today,
                    confidence=Confidence.HIGH,
                ),
                Observation(
                    entity=winter_entity, field="season", value="winter",
                    source_id="official_l2_winter", retrieved_at=today,
                    confidence=Confidence.CONFIRMED,
                ),
                Observation(
                    entity=winter_entity, field="headsign",
                    value="La Herradura – Punta de la Mona",
                    source_id="official_index", retrieved_at=today,
                    confidence=Confidence.HIGH,
                ),
                Observation(
                    entity=winter_entity, field="variant_code", value="NOMARINA",
                    source_id="official_l2_winter", retrieved_at=today,
                    confidence=Confidence.CONFIRMED,
                ),
                Observation(
                    entity=winter_entity, field="conditional",
                    value=(
                        "Winter routing. Marina del Este (Puerto Deportivo) is omitted: "
                        "the operator's winter page footnotes that stop with 'Esta parada "
                        "no se realiza en el horario de invierno'."
                    ),
                    source_id="official_l2_winter", retrieved_at=today,
                    confidence=Confidence.CONFIRMED,
                ),
                Observation(
                    entity=winter_entity, field="stop_sequence",
                    value=";".join(winter_sequence),
                    source_id="official_l2_winter", retrieved_at=today,
                    confidence=Confidence.MEDIUM,
                    derivation=(
                        "OSM relation 18496909 stop order, minus Marina del Este "
                        f"({marina}), per the operator's winter footnote."
                    ),
                    derived_from=f"{OSM_SOURCE_ID};official_l2_winter",
                    notes=(
                        "The winter geometry is assumed to be the summer geometry with "
                        "the port spur removed; that assumption is not itself sourced."
                    ),
                ),
            ]
    return rows


def _service_observations(today: dt.date) -> list[Observation]:
    rows: list[Observation] = []
    seen: set[str] = set()
    for timetable in official.TIMETABLES:
        if timetable.service_id in seen:
            continue
        seen.add(timetable.service_id)
        season_key = timetable.service_id.split("_")[0].lower()
        suffix = timetable.service_id.split("_", 1)[1]
        start, end = SEASONS[season_key]
        entity = f"service:{timetable.service_id}"
        rows += [
            Observation(
                entity=entity, field="weekdays", value=SERVICE_WEEKDAYS[suffix],
                source_id=timetable.source_id, retrieved_at=today,
                confidence=Confidence.HIGH,
                notes=(
                    "Sundays and public holidays share a timetable; the holiday "
                    "calendar itself is not published and is not modelled."
                    if suffix.startswith("SUNHOL")
                    else None
                ),
            ),
            Observation(
                entity=entity, field="start_date", value=start.isoformat(),
                source_id=timetable.source_id, retrieved_at=today,
                confidence=Confidence.CONFIRMED,
            ),
            Observation(
                entity=entity, field="end_date", value=end.isoformat(),
                source_id=timetable.source_id, retrieved_at=today,
                confidence=Confidence.CONFIRMED,
            ),
            Observation(
                entity=entity, field="description",
                value=f"{season_key} {suffix.replace('_', ' ').lower()}",
                source_id=timetable.source_id, retrieved_at=today,
                confidence=Confidence.HIGH,
            ),
        ]
    return rows


#: Which pattern each route's departures belong to, per season.
PATTERN_FOR: dict[tuple[str, str], str] = {
    ("ALM_1", "summer"): "ALM_1_CIRC",
    ("ALM_1", "winter"): "ALM_1_CIRC",
    ("ALM_2A", "summer"): "ALM_2A_CIRC",
    ("ALM_2A", "winter"): "ALM_2A_CIRC",
    ("ALM_2B", "summer"): "ALM_2B_CIRC_SUMMER",
    ("ALM_2B", "winter"): "ALM_2B_CIRC_WINTER",
    ("ALM_3A", "summer"): "ALM_3A_CIRC",
    ("ALM_3A", "winter"): "ALM_3A_CIRC",
    ("ALM_TORRECUEVAS", "summer"): "ALM_TORRECUEVAS_CIRC",
    ("ALM_TORRECUEVAS", "winter"): "ALM_TORRECUEVAS_CIRC",
}


def _departure_observations(today: dt.date, evidence_dir: Path) -> list[Observation]:
    rows: list[Observation] = []
    local = images_mod.by_source_url(evidence_dir)
    for timetable in official.TIMETABLES:
        pattern_id = PATTERN_FOR.get((timetable.route_id, timetable.season))
        if pattern_id is None:
            continue  # 3B and 3C have no reconstructed pattern to attach times to
        rows.append(
            Observation(
                entity=f"pattern:{pattern_id}",
                field=f"departures:{timetable.service_id}",
                value=";".join(timetable.departures),
                source_id=timetable.source_id,
                retrieved_at=today,
                confidence=Confidence.CONFIRMED,
                evidence_kind=EvidenceKind.TIMETABLE,
                source_url=timetable.image_url,
                notes=(
                    "Transcribed by hand from the operator's timetable image on "
                    f"{official.TRANSCRIBED_AT}. Departures from the principal stop. "
                    f"Image archived at images/{local[timetable.image_url].file}."
                    if timetable.image_url in local
                    else (
                        "Transcribed by hand from the operator's timetable image on "
                        f"{official.TRANSCRIBED_AT}. Departures from the principal stop."
                    )
                )
                + (f" {timetable.note}" if timetable.note else ""),
            )
        )
    return rows


def _shape_observations(evidence_dir: Path, today: dt.date) -> list[Observation]:
    """Write one GeoJSON LineString per pattern and cite it.

    Way members are stitched in relation order, flipping each way when its
    endpoints say it is traversed backwards. Anything that will not connect is
    left out rather than bridged with a straight line.
    """
    relations, nodes, ways = _load_relations(evidence_dir)
    geometry_dir = evidence_dir / "geometry"
    geometry_dir.mkdir(parents=True, exist_ok=True)
    rows: list[Observation] = []

    for relation_id, spec in OSM_RELATIONS.items():
        relation = relations[relation_id]
        way_ids = [m["ref"] for m in relation["members"] if m["type"] == "way"]
        points: list[tuple[float, float]] = []
        for way_id in way_ids:
            way = ways.get(way_id)
            if way is None:
                continue
            coords = [
                (nodes[n]["lat"], nodes[n]["lon"]) for n in way["nodes"] if n in nodes
            ]
            if len(coords) < 2:
                continue
            if points:
                # Choose the orientation whose first point is nearest the tail.
                head_gap = _gap(points[-1], coords[0])
                tail_gap = _gap(points[-1], coords[-1])
                if tail_gap < head_gap:
                    coords.reverse()
                if coords[0] == points[-1]:
                    coords = coords[1:]
            points.extend(coords)

        if len(points) < 2:
            continue
        shape_id = spec["pattern_id"]
        relative = f"geometry/{shape_id}.geojson"
        (geometry_dir / f"{shape_id}.geojson").write_text(
            json.dumps(
                {
                    "type": "Feature",
                    "properties": {
                        "shape_id": shape_id,
                        "osm_relation": relation_id,
                        "attribution": OSM_ATTRIBUTION,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[round(lon, 6), round(lat, 6)] for lat, lon in points],
                    },
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        rows.append(
            Observation(
                entity=f"shape:{shape_id}",
                field="geometry",
                value=relative,
                source_id=OSM_SOURCE_ID,
                retrieved_at=today,
                confidence=Confidence.MEDIUM,
                source_url=f"https://www.openstreetmap.org/relation/{relation_id}",
                derivation=(
                    f"Way members of relation {relation_id} stitched in relation order, "
                    f"each flipped when its endpoints indicate reverse traversal."
                ),
                notes=f"{len(points)} points. {OSM_ATTRIBUTION}.",
            )
        )
    return rows


def _gap(a: tuple[float, float], b: tuple[float, float]) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _agency_observations(today: dt.date) -> list[Observation]:
    return [
        Observation(
            entity="agency:ALM", field="agency_name",
            value="Autocares Urbanos Almuñécar", source_id="official_index",
            retrieved_at=today, confidence=Confidence.HIGH,
        ),
        Observation(
            entity="agency:ALM", field="agency_url", value="https://urbanosalmunecar.es/",
            source_id="official_index", retrieved_at=today, confidence=Confidence.CONFIRMED,
        ),
        Observation(
            entity="agency:ALM", field="agency_phone", value="+34 958 88 27 62",
            source_id="official_index", retrieved_at=today, confidence=Confidence.MEDIUM,
            notes="Published as 958882762 on the contact page.",
        ),
    ]


def ingest(
    data_dir: Path, *, refresh: bool = False, offline: bool = False
) -> tuple[int, int]:
    """Rebuild ``sources.yaml`` and ``observations.csv``. Returns their sizes.

    ``offline`` reuses the content hashes already recorded in ``sources.yaml``
    instead of fetching. CI runs it that way so that verifying reproducibility
    does not depend on the operator's site being up, or hammer it on every push.
    """
    evidence_dir = data_dir / "evidence"
    cache_dir = data_dir / "cache"
    today = official.TRANSCRIBED_AT

    hashes = {
        source.source_id: source.content_sha256
        for source in load_sources(evidence_dir / "sources.yaml")
        if source.content_sha256
    }
    if not offline:
        for page in official.PAGES:
            try:
                result = fetch(page.url, cache_dir / "official", force=refresh)
            except Exception:  # noqa: BLE001 - a failed fetch keeps the previous hash
                continue
            if result.status_code == 200:
                hashes[page.source_id] = result.normalized_sha256

    registry = load_or_create_registry(evidence_dir)

    observations = [
        *_agency_observations(today),
        *_route_observations(today),
        *_stop_observations(registry, today),
        *_pattern_observations(evidence_dir, registry, today),
        *_service_observations(today),
        *_departure_observations(today, evidence_dir),
        *_shape_observations(evidence_dir, today),
    ]
    sources = _sources(hashes, today)

    dump_sources(evidence_dir / "sources.yaml", sources)
    dump_observations(evidence_dir / "observations.csv", observations)
    return len(sources), len(observations)
