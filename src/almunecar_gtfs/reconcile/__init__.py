"""Reconciliation: evidence in, canonical network out.

This is the only place allowed to turn "what the sources say" into "what we
believe the network is". Scrapers write observations; this package writes
``data/canonical``; the GTFS builder reads only canonical data.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from almunecar_gtfs.models import Agency, FeedInfo, Network, Shape
from almunecar_gtfs.provenance import (
    Confidence,
    Conflict,
    EvidenceStore,
    dump_conflicts,
    merge_conflicts,
)
from almunecar_gtfs.reconcile.fields import Resolver, domain_for
from almunecar_gtfs.reconcile.patterns import reconcile_patterns
from almunecar_gtfs.reconcile.routes import reconcile_routes
from almunecar_gtfs.reconcile.schedules import reconcile_services, reconcile_trips
from almunecar_gtfs.reconcile.stops import reconcile_stops

__all__ = [
    "ReconcileResult",
    "load_publication_settings",
    "reconcile",
    "reconcile_patterns",
    "reconcile_routes",
    "reconcile_services",
    "reconcile_stops",
    "reconcile_trips",
]

PUBLICATION_FILE = "publication.yaml"

DEFAULT_PUBLICATION: dict[str, object] = {
    # Deliberately conservative: until Roalfa authorises publication, the feed
    # must not present itself as theirs.
    "authorized_by_operator": False,
    "feed_publisher_name": "almunecar-gtfs (unofficial community feed)",
    "feed_publisher_url": "https://github.com/rtoledano/almunecar-gtfs",
    "feed_contact_email": None,
    "feed_contact_url": None,
    "agency_id": "ALM",
}


def load_publication_settings(data_dir: Path) -> dict[str, object]:
    path = data_dir / PUBLICATION_FILE
    settings = dict(DEFAULT_PUBLICATION)
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        settings.update(loaded)
    return settings


@dataclass
class ReconcileResult:
    network: Network
    conflicts: list[Conflict]
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _load_shapes(evidence: EvidenceStore, evidence_dir: Path) -> tuple[list[Shape], list[str]]:
    """Shape geometry lives in GeoJSON files; observations point at them.

    Polylines are far too long for a readable CSV, but they still need
    provenance, so the observation records the source and the file path.
    """
    resolver = Resolver(evidence)
    shapes: list[Shape] = []

    for entity in evidence.entities("shape"):
        shape_id = entity.split(":", 1)[1]
        resolved = resolver.require(entity, "geometry")
        if resolved is None:
            continue
        path = evidence_dir / resolved.value
        if not path.exists():
            resolver.problems.append(f"{entity}: geometry file {path} does not exist")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            resolver.problems.append(f"{entity}: {path} is not valid JSON: {error}")
            continue

        geometry = payload.get("geometry", payload)
        if geometry.get("type") != "LineString":
            resolver.problems.append(f"{entity}: {path} is not a GeoJSON LineString")
            continue
        points = [(lat, lon) for lon, lat in geometry["coordinates"]]
        if len(points) < 2:
            resolver.problems.append(f"{entity}: {path} has fewer than two points")
            continue
        shapes.append(
            Shape(
                shape_id=shape_id,
                points=points,
                source_id=resolved.source_id,
                confidence=resolved.confidence,
            )
        )

    return sorted(shapes, key=lambda s: s.shape_id), resolver.problems


def _reconcile_agency(
    evidence: EvidenceStore, settings: dict[str, object]
) -> tuple[Agency, list[str]]:
    resolver = Resolver(evidence)
    agency_entities = evidence.entities("agency")
    agency_id = str(settings.get("agency_id", "ALM"))
    if not agency_entities:
        resolver.problems.append("no agency evidence recorded")
        return (
            Agency(
                agency_id=agency_id,
                agency_name="Unknown operator",
                agency_url="https://example.invalid",
                is_official_feed=False,
            ),
            resolver.problems,
        )

    entity = agency_entities[0]
    if len(agency_entities) > 1:
        resolver.problems.append(
            f"multiple agency entities recorded ({', '.join(agency_entities)}); using {entity}"
        )
    name = resolver.require(entity, "agency_name")
    url = resolver.require(entity, "agency_url")
    return (
        Agency(
            agency_id=entity.split(":", 1)[1],
            agency_name=name.value if name else "Unknown operator",
            agency_url=url.value if url else "https://example.invalid",
            agency_phone=resolver.value(entity, "agency_phone"),
            agency_email=resolver.value(entity, "agency_email"),
            is_official_feed=bool(settings.get("authorized_by_operator", False)),
        ),
        resolver.problems,
    )


def _feed_info(
    evidence: EvidenceStore, network_services, settings: dict[str, object]
) -> FeedInfo:
    """Feed version is the latest source retrieval date, so it is both
    deterministic and a truthful statement about how current the data is."""
    retrievals = [observation.retrieved_at for observation in evidence.observations]
    version_date = max(retrievals) if retrievals else dt.date.today()
    return FeedInfo(
        feed_publisher_name=str(settings["feed_publisher_name"]),
        feed_publisher_url=str(settings["feed_publisher_url"]),
        feed_version=version_date.isoformat(),
        feed_start_date=min((s.start_date for s in network_services), default=None),
        feed_end_date=max((s.end_date for s in network_services), default=None),
        feed_contact_email=settings.get("feed_contact_email") or None,
        feed_contact_url=settings.get("feed_contact_url") or None,
    )


def reconcile(evidence: EvidenceStore, data_dir: Path) -> ReconcileResult:
    """Produce the canonical network and the conflict register from evidence."""
    evidence_dir = data_dir / "evidence"
    settings = load_publication_settings(data_dir)

    agency, agency_problems = _reconcile_agency(evidence, settings)
    stops, stop_problems = reconcile_stops(evidence)
    routes, route_problems = reconcile_routes(evidence)
    patterns, pattern_problems = reconcile_patterns(evidence)
    services, service_problems = reconcile_services(evidence)
    trips, trip_problems = reconcile_trips(
        evidence, patterns, {service.service_id for service in services}
    )
    shapes, shape_problems = _load_shapes(evidence, evidence_dir)

    network = Network(
        agency=agency,
        feed_info=_feed_info(evidence, services, settings),
        stops=stops,
        routes=routes,
        patterns=patterns,
        services=services,
        trips=trips,
        shapes=shapes,
    )

    detected = evidence.detect_conflicts(domain_for)
    conflicts = merge_conflicts(evidence.conflicts, detected)

    return ReconcileResult(
        network=network,
        conflicts=conflicts,
        problems=[
            *agency_problems,
            *stop_problems,
            *route_problems,
            *pattern_problems,
            *service_problems,
            *trip_problems,
            *shape_problems,
        ],
    )


def write_conflicts(evidence_dir: Path, conflicts: list[Conflict]) -> None:
    dump_conflicts(evidence_dir / "conflicts.yaml", conflicts)


# Re-exported for convenience in notebooks and ad-hoc scripts.
LOW = Confidence.LOW
