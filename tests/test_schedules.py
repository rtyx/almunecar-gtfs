"""Timetable and calendar invariants (plan tasks 7, 8 and 10)."""

from __future__ import annotations

import datetime as dt

import pytest

from almunecar_gtfs import qa
from almunecar_gtfs.models import ServicePeriod
from almunecar_gtfs.provenance import EvidenceStore
from almunecar_gtfs.reconcile.schedules import (
    make_trip_id,
    reconcile_services,
    reconcile_trips,
)

from .conftest import FIXTURE_SOURCES, observation


def test_service_period_rejects_an_end_before_its_start():
    with pytest.raises(ValueError, match="end_date precedes"):
        ServicePeriod(
            service_id="X",
            start_date=dt.date(2026, 9, 16),
            end_date=dt.date(2026, 7, 1),
        )


def test_weekday_tokens_become_calendar_flags(evidence):
    services, problems = reconcile_services(evidence)
    assert problems == []
    service = services[0]
    assert service.weekday_flags == (True, True, True, True, True, False, False)


def test_calendar_coverage_respects_added_and_removed_dates():
    service = ServicePeriod(
        service_id="X",
        monday=True,
        start_date=dt.date(2026, 7, 1),
        end_date=dt.date(2026, 9, 15),
        added_dates=[dt.date(2026, 8, 15)],
        removed_dates=[dt.date(2026, 8, 3)],
    )
    assert service.covers(dt.date(2026, 8, 10))       # a Monday inside the period
    assert not service.covers(dt.date(2026, 8, 11))   # a Tuesday
    assert service.covers(dt.date(2026, 8, 15))       # explicitly added Saturday
    assert not service.covers(dt.date(2026, 8, 3))    # explicitly removed Monday


def test_trip_ids_are_composed_from_meaning_not_position(network):
    pattern = network.patterns_by_id["ALM_9_OUT"]
    assert make_trip_id(pattern, "SUMMER_WD", "08:30:00") == "ALM_9_SUMMER_WD_OUT_0830"


def test_a_pattern_variant_gets_its_own_trip_ids(network):
    pattern = network.patterns_by_id["ALM_9_OUT"].model_copy(update={"variant_code": "CABRIA"})
    assert make_trip_id(pattern, "SUMMER_WD", "10:00:00") == "ALM_9_SUMMER_WD_OUT_CABRIA_1000"


def test_after_midnight_departures_keep_gtfs_hour_overflow(network):
    pattern = network.patterns_by_id["ALM_9_OUT"]
    assert make_trip_id(pattern, "SUMMER_WD", "25:15:00") == "ALM_9_SUMMER_WD_OUT_2515"


def test_departures_produce_one_trip_each(network):
    trips = [t for t in network.trips if t.pattern_id == "ALM_9_OUT"]
    assert [t.departure for t in trips] == ["07:30:00", "08:30:00", "09:30:00"]
    assert all(t.service_id == "ALLYEAR_WD" for t in trips)


def test_departures_for_an_unknown_service_are_refused(network):
    store = EvidenceStore(
        sources=FIXTURE_SOURCES,
        observations=[observation("pattern:ALM_9_OUT", "departures:NOPE", "07:00")],
    )
    trips, problems = reconcile_trips(store, [network.patterns_by_id["ALM_9_OUT"]], set())
    assert trips == []
    assert any("unknown service" in problem for problem in problems)


def test_the_feed_must_cover_the_required_future_horizon(network):
    findings = qa.check_calendars(network, today=dt.date(2026, 8, 10))
    assert [f for f in findings if f.code == "calendar.horizon_too_short"] == []


def test_a_feed_that_expires_too_soon_is_an_error(network):
    short = network.services[0].model_copy(update={"end_date": dt.date(2026, 8, 20)})
    trimmed = network.model_copy(update={"services": [short]})
    findings = qa.check_calendars(trimmed, today=dt.date(2026, 8, 10))
    assert any(f.code == "calendar.horizon_too_short" for f in findings)


def test_a_gap_between_seasons_is_reported():
    """A summer calendar ending before the winter one starts leaves passengers
    with no service at all on the days in between."""
    from almunecar_gtfs.models import (
        Agency,
        FeedInfo,
        Network,
        Pattern,
        PatternStop,
        Route,
        Season,
        TimingMethod,
        TimingModel,
        TripDeparture,
    )

    pattern = Pattern(
        pattern_id="P",
        route_id="R",
        direction_id=0,
        season=Season.SUMMER,
        headsign="X",
        stops=[
            PatternStop(stop_id="ALM_0001", offset_seconds=0, timing_method=TimingMethod.PUBLISHED),
            PatternStop(
                stop_id="ALM_0002", offset_seconds=300, timing_method=TimingMethod.PUBLISHED
            ),
        ],
        timing_model=TimingModel(method=TimingMethod.PUBLISHED, description="fixture"),
    )
    network = Network(
        agency=Agency(agency_id="ALM", agency_name="x", agency_url="https://example.invalid"),
        feed_info=FeedInfo(
            feed_publisher_name="x", feed_publisher_url="https://example.invalid", feed_version="1"
        ),
        routes=[Route(route_id="R", route_short_name="R", route_long_name="Fixture")],
        patterns=[pattern],
        services=[
            ServicePeriod(
                service_id="SUMMER",
                monday=True,
                tuesday=True,
                wednesday=True,
                thursday=True,
                friday=True,
                saturday=True,
                sunday=True,
                start_date=dt.date(2026, 7, 1),
                end_date=dt.date(2026, 8, 20),
            ),
            ServicePeriod(
                service_id="WINTER",
                monday=True,
                tuesday=True,
                wednesday=True,
                thursday=True,
                friday=True,
                saturday=True,
                sunday=True,
                start_date=dt.date(2026, 8, 25),
                end_date=dt.date(2027, 6, 30),
            ),
        ],
        trips=[
            TripDeparture(
                trip_id="T1",
                pattern_id="P",
                service_id="SUMMER",
                departure="08:00:00",
                source_id="fixture_operator",
            ),
            TripDeparture(
                trip_id="T2",
                pattern_id="P",
                service_id="WINTER",
                departure="08:00:00",
                source_id="fixture_operator",
            ),
        ],
    )
    findings = qa.check_calendars(network, today=dt.date(2026, 8, 10))
    gaps = [f for f in findings if f.code == "calendar.gap"]
    assert gaps, "the 21-24 August hole should be reported"
    assert "2026-08-21" in gaps[0].message


def test_a_trip_referencing_an_unknown_service_is_an_error(network):
    broken = network.trips[0].model_copy(update={"service_id": "NOPE"})
    findings = qa.check_trips(network.model_copy(update={"trips": [broken]}))
    assert any(f.code == "trip.unknown_service" for f in findings)
