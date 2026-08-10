"""Reconcile observations into canonical routes.

A route number that only a stale page still uses is recorded in
``former_short_names``; it is never promoted to the current designation because
no newer source happened to contradict it.
"""

from __future__ import annotations

from almunecar_gtfs.models import PublicationStatus, Route, Season
from almunecar_gtfs.provenance import EvidenceStore
from almunecar_gtfs.reconcile.fields import Resolver


def reconcile_routes(evidence: EvidenceStore) -> tuple[list[Route], list[str]]:
    resolver = Resolver(evidence)
    routes: list[Route] = []

    for entity in evidence.entities("route"):
        route_id = entity.split(":", 1)[1]
        short_name = resolver.require(entity, "route_short_name")
        long_name = resolver.require(entity, "route_long_name")
        if short_name is None or long_name is None:
            continue

        seasons: list[Season] = []
        for token in resolver.value(entity, "seasons", []):
            try:
                seasons.append(Season(token))
            except ValueError:
                resolver.problems.append(f"{entity}: unknown season {token!r}")

        status_text = resolver.value(entity, "status", PublicationStatus.PUBLISHABLE.value)
        try:
            status = PublicationStatus(status_text)
        except ValueError:
            resolver.problems.append(f"{entity}: unknown status {status_text!r}")
            status = PublicationStatus.NOT_PUBLISHABLE

        routes.append(
            Route(
                route_id=route_id,
                route_short_name=short_name.value,
                route_long_name=long_name.value,
                route_desc=resolver.value(entity, "route_desc"),
                seasons=seasons,
                status=status,
                former_short_names=resolver.value(entity, "former_short_names", []),
            )
        )

    return sorted(routes, key=lambda r: r.route_id), resolver.problems
