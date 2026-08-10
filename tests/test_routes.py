"""Route invariants (plan tasks 3 and 10)."""

from __future__ import annotations

import datetime as dt

import pytest

from almunecar_gtfs import qa
from almunecar_gtfs.models import PublicationStatus, Route, Season
from almunecar_gtfs.provenance import (
    Claim,
    Confidence,
    Conflict,
    EvidenceStore,
    merge_conflicts,
)
from almunecar_gtfs.reconcile.fields import domain_for
from almunecar_gtfs.reconcile.routes import reconcile_routes

from .conftest import FIXTURE_SOURCES, TODAY, observation


def test_route_type_must_be_a_valid_gtfs_value():
    with pytest.raises(ValueError, match="route_type"):
        Route(
            route_id="ALM_9",
            route_short_name="9",
            route_long_name="Fixture",
            route_type=99,
        )


def test_reconciled_route_carries_its_seasons(network):
    route = network.routes_by_id["ALM_9"]
    assert route.seasons == [Season.SUMMER, Season.WINTER]
    assert route.status is PublicationStatus.PUBLISHABLE


def test_every_route_has_at_least_one_trip(network):
    assert [f for f in qa.check_routes(network) if f.code == "route.no_trips"] == []


def test_a_route_without_trips_is_an_error(network):
    stripped = network.model_copy(update={"trips": []})
    codes = {f.code for f in qa.check_routes(stripped)}
    assert "route.no_trips" in codes


def test_former_route_numbers_are_recorded_not_promoted():
    """A stale page calling Torrecuevas 'line 5' must not become the current name."""
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("route:ALM_4", "route_short_name", "4"),
            observation("route:ALM_4", "route_long_name", "Torrecuevas fixture"),
            observation("route:ALM_4", "former_short_names", "5"),
        ],
    )
    routes, problems = reconcile_routes(store)
    assert problems == []
    assert routes[0].route_short_name == "4"
    assert routes[0].former_short_names == ["5"]


def test_disagreeing_sources_produce_a_conflict_record():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("route:ALM_4", "route_short_name", "4"),
            observation(
                "route:ALM_4",
                "route_short_name",
                "5",
                source_id="fixture_stale_operator",
                retrieved_at=dt.date(2023, 5, 1),
            ),
        ],
    )
    conflicts = store.detect_conflicts(domain_for)
    assert len(conflicts) == 1
    assert {claim.value for claim in conflicts[0].claims} == {"4", "5"}
    assert conflicts[0].status == "unresolved"


def test_agreeing_sources_produce_no_conflict():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("route:ALM_4", "route_short_name", "4"),
            observation("route:ALM_4", "route_short_name", "4", source_id="fixture_moovit"),
        ],
    )
    assert store.detect_conflicts(domain_for) == []


def _conflict(value_a: str, value_b: str, **kwargs) -> Conflict:
    return Conflict(
        entity="route:ALM_4",
        field="route_short_name",
        claims=[
            Claim(
                source_id="fixture_operator",
                value=value_a,
                retrieved_at=TODAY,
                confidence=Confidence.HIGH,
            ),
            Claim(
                source_id="fixture_stale_operator",
                value=value_b,
                retrieved_at=dt.date(2023, 5, 1),
                confidence=Confidence.CONFIRMED,
            ),
        ],
        **kwargs,
    )


def test_merging_preserves_a_human_resolution():
    existing = [
        _conflict(
            "4",
            "5",
            status="resolved",
            resolution="Current operator page supersedes the 2023 page.",
            resolved_value="4",
            resolved_at=TODAY,
        )
    ]
    merged = merge_conflicts(existing, [_conflict("4", "5")])
    assert merged[0].status == "resolved"
    assert merged[0].resolved_value == "4"


def test_a_resolved_conflict_reopens_when_the_claims_change():
    existing = [
        _conflict(
            "4",
            "5",
            status="resolved",
            resolution="Current operator page supersedes the 2023 page.",
            resolved_value="4",
            resolved_at=TODAY,
        )
    ]
    merged = merge_conflicts(existing, [_conflict("4", "6")])
    assert merged[0].status == "unresolved"
    assert "REOPENED" in merged[0].resolution


def test_conflicts_that_stop_reproducing_are_kept_not_deleted():
    merged = merge_conflicts([_conflict("4", "5")], [])
    assert len(merged) == 1
    assert merged[0].status == "accepted_ambiguity"


def test_a_blocking_conflict_marks_its_entity_unpublishable():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        conflicts=[_conflict("4", "5", blocks_publication=True)],
    )
    assert store.blocking_entities() == {"route:ALM_4"}
