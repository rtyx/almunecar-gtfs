"""Stop registry invariants (plan tasks 4 and 10)."""

from __future__ import annotations

import datetime as dt

import pytest

from almunecar_gtfs import qa
from almunecar_gtfs.models import Stop
from almunecar_gtfs.provenance import (
    Confidence,
    EvidenceDomain,
    EvidenceKind,
    EvidenceStore,
    Observation,
    Source,
    is_disqualified,
)
from almunecar_gtfs.reconcile.stops import reconcile_stops

from .conftest import FIXTURE_SOURCES, TODAY, observation


def make_stop(stop_id: str, latitude: float, longitude: float, name: str = "X") -> Stop:
    return Stop(
        internal_stop_id=stop_id,
        name=name,
        latitude=latitude,
        longitude=longitude,
        municipality="Almuñécar",
        confidence=Confidence.HIGH,
        source_id="fixture_ibus",
    )


def test_stop_ids_are_stable_and_not_derived_from_names():
    with pytest.raises(ValueError, match="ALM_0001"):
        make_stop("playa-velilla", 36.73, -3.69)


def test_coordinates_must_be_valid_wgs84():
    with pytest.raises(ValueError, match="latitude"):
        make_stop("ALM_0001", 91.0, -3.69)
    with pytest.raises(ValueError, match="longitude"):
        make_stop("ALM_0001", 36.73, -181.0)


def test_reconciled_stops_are_inside_the_service_area(network):
    findings = qa.check_stops(network)
    assert [f for f in findings if f.code == "stop.outside_service_area"] == []


def test_stop_outside_the_service_area_is_an_error():
    from almunecar_gtfs.models import Agency, FeedInfo, Network

    stray = make_stop("ALM_9999", 40.4168, -3.7038, name="Madrid")
    network = Network(
        agency=Agency(agency_id="ALM", agency_name="x", agency_url="https://example.invalid"),
        feed_info=FeedInfo(
            feed_publisher_name="x", feed_publisher_url="https://example.invalid", feed_version="1"
        ),
        stops=[stray],
    )
    codes = {f.code for f in qa.check_stops(network)}
    assert "stop.outside_service_area" in codes


def test_same_name_stops_far_apart_are_flagged():
    from almunecar_gtfs.models import Agency, FeedInfo, Network

    network = Network(
        agency=Agency(agency_id="ALM", agency_name="x", agency_url="https://example.invalid"),
        feed_info=FeedInfo(
            feed_publisher_name="x", feed_publisher_url="https://example.invalid", feed_version="1"
        ),
        stops=[
            make_stop("ALM_0001", 36.7350, -3.6890, name="Playa"),
            make_stop("ALM_0002", 36.7290, -3.7350, name="Playa"),
        ],
    )
    findings = qa.check_stops(network)
    assert any(f.code == "stop.same_name_far_apart" for f in findings)


def test_distinct_stops_within_ten_metres_are_flagged_as_near_duplicates():
    from almunecar_gtfs.models import Agency, FeedInfo, Network

    network = Network(
        agency=Agency(agency_id="ALM", agency_name="x", agency_url="https://example.invalid"),
        feed_info=FeedInfo(
            feed_publisher_name="x", feed_publisher_url="https://example.invalid", feed_version="1"
        ),
        stops=[
            make_stop("ALM_0001", 36.735000, -3.689000, name="A"),
            make_stop("ALM_0002", 36.735020, -3.689010, name="B"),
        ],
    )
    findings = qa.check_stops(network)
    assert any(f.code == "stop.near_duplicate" for f in findings)


def test_opposite_side_of_the_road_stays_two_stops(network):
    """A direction pair is 20-40 m apart, which must not trip the duplicate check."""
    from almunecar_gtfs.models import Agency, FeedInfo, Network

    pair = Network(
        agency=Agency(agency_id="ALM", agency_name="x", agency_url="https://example.invalid"),
        feed_info=FeedInfo(
            feed_publisher_name="x", feed_publisher_url="https://example.invalid", feed_version="1"
        ),
        stops=[
            make_stop("ALM_0001", 36.735000, -3.689000, name="Cruce"),
            make_stop("ALM_0002", 36.735000, -3.689280, name="Cruce"),
        ],
    )
    findings = qa.check_stops(pair)
    assert not any(f.code == "stop.near_duplicate" for f in findings)
    # Same name, ~25 m apart: under the 100 m threshold, so no false alarm either.
    assert not any(f.code == "stop.same_name_far_apart" for f in findings)


def test_poi_coordinates_are_disqualified_as_stop_evidence():
    assert is_disqualified(EvidenceDomain.STOP_COORD, "moovit", EvidenceKind.POI)
    assert not is_disqualified(
        EvidenceDomain.STOP_COORD, "osm", EvidenceKind.BUS_STOP_NODE
    )


def test_a_stop_backed_only_by_a_poi_coordinate_is_refused():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("stop:ALM_0001", "name", "Hotel Fixture"),
            observation(
                "stop:ALM_0001",
                "coordinate",
                "36.7350,-3.6890",
                source_id="fixture_moovit",
                evidence_kind=EvidenceKind.POI,
            ),
        ],
    )
    stops, problems = reconcile_stops(store)
    assert stops == []
    assert any("disqualified coordinate evidence" in problem for problem in problems)


def test_a_poi_coordinate_confirmed_by_another_source_is_accepted_at_low_confidence():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("stop:ALM_0001", "name", "Hotel Fixture"),
            observation(
                "stop:ALM_0001",
                "coordinate",
                "36.735000,-3.689000",
                source_id="fixture_moovit",
                evidence_kind=EvidenceKind.POI,
            ),
            observation(
                "stop:ALM_0001",
                "coordinate",
                "36.735100,-3.689050",
                source_id="fixture_osm",
                evidence_kind=EvidenceKind.POI,
            ),
        ],
    )
    stops, problems = reconcile_stops(store)
    assert problems == []
    assert len(stops) == 1
    assert stops[0].confidence is Confidence.LOW


def test_explicit_stop_coordinate_beats_an_osm_node():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            observation("stop:ALM_0001", "name", "Fixture"),
            observation(
                "stop:ALM_0001",
                "coordinate",
                "36.735000,-3.689000",
                source_id="fixture_ibus",
                evidence_kind=EvidenceKind.STOP_COORDINATE,
                confidence=Confidence.MEDIUM,
            ),
            observation(
                "stop:ALM_0001",
                "coordinate",
                "36.736000,-3.690000",
                source_id="fixture_osm",
                evidence_kind=EvidenceKind.BUS_STOP_NODE,
                confidence=Confidence.CONFIRMED,
            ),
        ],
    )
    stops, problems = reconcile_stops(store)
    assert problems == []
    # Hierarchy beats confidence: a medium-confidence explicit platform coordinate
    # still outranks a confirmed OSM node.
    assert stops[0].source_id == "fixture_ibus"


def test_a_stale_operator_page_loses_to_a_current_one():
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[
            Observation(
                entity="route:ALM_4",
                field="route_short_name",
                value="5",
                source_id="fixture_stale_operator",
                retrieved_at=dt.date(2023, 5, 1),
                confidence=Confidence.CONFIRMED,
            ),
            Observation(
                entity="route:ALM_4",
                field="route_short_name",
                value="4",
                source_id="fixture_operator",
                retrieved_at=TODAY,
                confidence=Confidence.HIGH,
            ),
        ],
    )
    best = store.best(EvidenceDomain.SCHEDULE, "route:ALM_4", "route_short_name")
    assert best is not None
    assert best.value == "4"


def test_unregistered_sources_are_rejected_at_load_time():
    with pytest.raises(ValueError, match="unregistered source_id"):
        EvidenceStore(
            sources=[
                Source(
                    source_id="known",
                    source_type="official",
                    source_url="https://example.invalid",
                    title="Known",
                )
            ],
            observations=[
                Observation(
                    entity="stop:ALM_0001",
                    field="name",
                    value="x",
                    source_id="typo_source",
                    retrieved_at=TODAY,
                )
            ],
        )
