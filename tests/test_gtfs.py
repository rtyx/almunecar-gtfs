"""GTFS generation invariants (plan tasks 9, 10 and 11)."""

from __future__ import annotations

import csv
import io
import zipfile

import pytest

from almunecar_gtfs import dataset, qa
from almunecar_gtfs.gtfs import build as build_mod
from almunecar_gtfs.gtfs.validate import ValidatorNotAvailable, find_validator_jar, parse_report


def rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


@pytest.fixture
def feed(network):
    return build_mod.build_feed(network)


def test_all_required_files_are_present(feed):
    assert set(feed) >= build_mod.REQUIRED_GTFS_FILES
    assert "shapes.txt" in feed
    assert "feed_info.txt" in feed


def test_agency_uses_the_local_timezone_and_language(feed):
    agency = rows(feed["agency.txt"])[0]
    assert agency["agency_timezone"] == "Europe/Madrid"
    assert agency["agency_lang"] == "es"


def test_routes_are_buses(feed):
    assert all(route["route_type"] == "3" for route in rows(feed["routes.txt"]))


def test_every_trip_belongs_to_a_declared_route_and_service(feed):
    route_ids = {route["route_id"] for route in rows(feed["routes.txt"])}
    service_ids = {service["service_id"] for service in rows(feed["calendar.txt"])}
    for trip in rows(feed["trips.txt"]):
        assert trip["route_id"] in route_ids
        assert trip["service_id"] in service_ids


def test_every_referenced_stop_exists(feed):
    stop_ids = {stop["stop_id"] for stop in rows(feed["stops.txt"])}
    for stop_time in rows(feed["stop_times.txt"]):
        assert stop_time["stop_id"] in stop_ids


def test_every_referenced_shape_exists(feed):
    shape_ids = {shape["shape_id"] for shape in rows(feed["shapes.txt"])}
    for trip in rows(feed["trips.txt"]):
        if trip["shape_id"]:
            assert trip["shape_id"] in shape_ids


def test_stop_sequences_strictly_increase_and_times_never_go_backwards(feed):
    by_trip: dict[str, list[dict[str, str]]] = {}
    for stop_time in rows(feed["stop_times.txt"]):
        by_trip.setdefault(stop_time["trip_id"], []).append(stop_time)

    assert by_trip
    for trip_id, stop_times in by_trip.items():
        sequences = [int(s["stop_sequence"]) for s in stop_times]
        assert sequences == sorted(sequences), trip_id
        assert len(set(sequences)) == len(sequences), trip_id
        assert len(stop_times) >= 2, trip_id
        times = [s["departure_time"] for s in stop_times]
        assert times == sorted(times), trip_id
        assert all(times), trip_id


def test_derived_times_are_marked_as_estimates_not_timepoints(feed):
    stop_times = rows(feed["stop_times.txt"])
    flags = [s["timepoint"] for s in stop_times if s["trip_id"] == "ALM_9_ALLYEAR_WD_OUT_0730"]
    assert flags == ["1", "0", "0", "1"]


def test_stop_times_are_the_origin_departure_plus_the_pattern_offset(feed):
    stop_times = [
        s for s in rows(feed["stop_times.txt"]) if s["trip_id"] == "ALM_9_ALLYEAR_WD_OUT_0830"
    ]
    assert [s["departure_time"] for s in stop_times] == [
        "08:30:00",
        "08:34:00",
        "08:38:00",
        "08:45:00",
    ]


def test_shape_dist_traveled_increases_along_the_trip(feed):
    stop_times = [
        s for s in rows(feed["stop_times.txt"]) if s["trip_id"] == "ALM_9_ALLYEAR_WD_OUT_0730"
    ]
    distances = [float(s["shape_dist_traveled"]) for s in stop_times]
    assert distances == sorted(distances)
    assert distances[0] == 0.0


def test_a_pattern_with_unknown_timings_never_reaches_the_feed(network):
    from almunecar_gtfs.models import PublicationStatus

    pattern = network.patterns_by_id["ALM_9_OUT"]
    unusable = pattern.model_copy(
        update={
            "stops": [
                pattern.stops[0],
                pattern.stops[1].model_copy(update={"offset_seconds": None}),
                *pattern.stops[2:],
            ],
            "status": PublicationStatus.NOT_PUBLISHABLE,
        }
    )
    stripped = network.model_copy(update={"patterns": [unusable]})
    with pytest.raises(build_mod.BuildError, match="no publishable trips"):
        build_mod.build_feed(stripped)


def test_gtfs_times_may_exceed_twenty_four_hours():
    assert build_mod.format_time(25 * 3600 + 15 * 60) == "25:15:00"


def test_the_build_is_deterministic(network, tmp_path):
    first = build_mod.write_zip(tmp_path / "a.zip", build_mod.build_feed(network))
    second = build_mod.write_zip(tmp_path / "b.zip", build_mod.build_feed(network))
    assert first.read_bytes() == second.read_bytes()


def test_the_zip_contains_only_gtfs_files_with_fixed_timestamps(network, tmp_path):
    path = build_mod.write_zip(tmp_path / "feed.zip", build_mod.build_feed(network))
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
    assert {info.filename for info in infos} <= set(build_mod.GTFS_FILES)
    assert all(info.date_time == build_mod.ZIP_TIMESTAMP for info in infos)


def test_canonical_data_round_trips_through_disk(network, tmp_path):
    canonical = tmp_path / "canonical"
    dataset.write_network(canonical, network)
    reloaded = dataset.read_network(canonical)
    assert reloaded.model_dump() == network.model_dump()


def test_canonical_serialisation_is_stable(network, tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    dataset.write_network(first, network)
    dataset.write_network(second, dataset.read_network(first))
    for name in first.iterdir():
        assert name.read_bytes() == (second / name.name).read_bytes(), name.name


def test_the_whole_dataset_passes_qa(network, evidence):
    findings = qa.check_all(network, evidence)
    assert qa.errors(findings) == []


def test_provenance_is_required_for_every_stop_coordinate(network):
    from almunecar_gtfs.provenance import EvidenceStore

    empty = EvidenceStore(sources=[], observations=[])
    findings = qa.check_provenance(network, empty)
    assert any(f.code == "provenance.stop_coordinate" for f in findings)


def test_the_validator_reports_a_clear_error_when_it_is_not_installed(monkeypatch):
    monkeypatch.delenv("GTFS_VALIDATOR_JAR", raising=False)
    with pytest.raises(ValidatorNotAvailable, match="No GTFS validator jar"):
        find_validator_jar()


def test_validator_reports_are_parsed(tmp_path):
    report = tmp_path / "report.json"
    report.write_text(
        '{"notices": [{"code": "missing_required_file", "severity": "ERROR", '
        '"totalNotices": 2, "sampleNotices": []}]}',
        encoding="utf-8",
    )
    notices = parse_report(report)
    assert notices[0].code == "missing_required_file"
    assert notices[0].total == 2
