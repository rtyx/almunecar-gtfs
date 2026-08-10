"""Reconcile observations into the canonical physical stop registry.

One record per physical boarding location. Two poles facing each other across a
road are two stops with two ids, even when the operator prints one name on both.
"""

from __future__ import annotations

from almunecar_gtfs.models import PublicationStatus, Stop, haversine_m
from almunecar_gtfs.provenance import (
    Confidence,
    EvidenceDomain,
    EvidenceStore,
    is_disqualified,
)
from almunecar_gtfs.reconcile.fields import Resolver

#: Two independent sources whose coordinates agree within this distance count as
#: corroboration, which is what lets otherwise-disqualified POI evidence through.
CORROBORATION_RADIUS_M = 30.0


def _corroborated_coordinate(
    evidence: EvidenceStore, entity: str
) -> tuple[tuple[float, float], str, Confidence] | None:
    """Rescue a stop whose only coordinate evidence is disqualified.

    "Never use an ordinary POI coordinate as evidence for a stop without
    additional confirmation" — so a POI coordinate is usable only when a
    *different* source independently puts the stop in the same place. The result
    is deliberately downgraded to low confidence.
    """
    from almunecar_gtfs.reconcile.fields import parse_coordinate

    candidates: list[tuple[str, tuple[float, float]]] = []
    for observation in evidence.ranked(EvidenceDomain.STOP_COORD, entity, "coordinate"):
        try:
            candidates.append((observation.source_id, parse_coordinate(observation.value)))
        except ValueError:
            continue

    for index, (source_id, point) in enumerate(candidates):
        for other_source, other_point in candidates[index + 1 :]:
            if other_source == source_id:
                continue
            if haversine_m(point[0], point[1], other_point[0], other_point[1]) <= (
                CORROBORATION_RADIUS_M
            ):
                return point, source_id, Confidence.LOW
    return None


def reconcile_stops(evidence: EvidenceStore) -> tuple[list[Stop], list[str]]:
    """Build every stop the evidence supports; report the ones it does not."""
    resolver = Resolver(evidence)
    stops: list[Stop] = []

    for entity in evidence.entities("stop"):
        stop_id = entity.split(":", 1)[1]
        name = resolver.require(entity, "name")
        if name is None:
            continue

        coordinate = resolver.resolve(entity, "coordinate")
        if coordinate is not None:
            latitude, longitude = coordinate.value
            source_id = coordinate.source_id
            confidence = coordinate.confidence
        else:
            observations = evidence.for_field(entity, "coordinate")
            if not observations:
                resolver.problems.append(f"{entity}: no coordinate evidence at all")
                continue
            rescued = _corroborated_coordinate(evidence, entity)
            if rescued is None:
                blocked = {
                    observation.source_id
                    for observation in observations
                    if is_disqualified(
                        EvidenceDomain.STOP_COORD,
                        evidence.source_of(observation).source_type,
                        observation.evidence_kind,
                    )
                }
                resolver.problems.append(
                    f"{entity}: only disqualified coordinate evidence "
                    f"({', '.join(sorted(blocked)) or 'unparseable values'}); "
                    f"a POI coordinate needs independent confirmation before it can "
                    f"become a bus stop"
                )
                continue
            (latitude, longitude), source_id, confidence = rescued

        status_text = resolver.value(entity, "status", PublicationStatus.PUBLISHABLE.value)
        try:
            status = PublicationStatus(status_text)
        except ValueError:
            resolver.problems.append(f"{entity}: unknown status {status_text!r}")
            status = PublicationStatus.NOT_PUBLISHABLE

        stops.append(
            Stop(
                internal_stop_id=stop_id,
                name=name.value,
                latitude=latitude,
                longitude=longitude,
                municipality=resolver.value(entity, "municipality", "Almuñécar"),
                confidence=confidence,
                source_id=source_id,
                osm_node_id=resolver.value(entity, "osm_node_id"),
                ibus_stop_id=resolver.value(entity, "ibus_stop_id"),
                direction_hint=resolver.value(entity, "direction_hint"),
                pair_stop_id=resolver.value(entity, "pair_stop_id"),
                status=status,
            )
        )

    return sorted(stops, key=lambda s: s.internal_stop_id), resolver.problems
