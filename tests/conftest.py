"""Shared fixtures.

Everything here is **synthetic**. The coordinates and times are plausible for
the area only so that bounding-box and geometry checks exercise realistic
numbers; none of it is transit data and none of it may be copied into
``data/evidence``.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from almunecar_gtfs.provenance import (
    Confidence,
    EvidenceKind,
    EvidenceStore,
    Observation,
    Source,
)

TODAY = dt.date(2026, 8, 9)
SEASON_START = dt.date(2026, 7, 1)
SEASON_END = dt.date(2027, 6, 30)

FIXTURE_SOURCES = [
    Source(
        source_id="fixture_operator",
        source_type="official",
        source_url="https://example.invalid/operator",
        title="Fixture operator page",
        retrieved_at=TODAY,
    ),
    Source(
        source_id="fixture_ibus",
        source_type="ibusgps",
        source_url="https://example.invalid/ibus",
        title="Fixture iBusGPS",
        retrieved_at=TODAY,
    ),
    Source(
        source_id="fixture_osm",
        source_type="osm",
        source_url="https://example.invalid/osm",
        title="Fixture OpenStreetMap",
        retrieved_at=TODAY,
    ),
    Source(
        source_id="fixture_moovit",
        source_type="moovit",
        source_url="https://example.invalid/moovit",
        title="Fixture Moovit",
        retrieved_at=TODAY,
    ),
    Source(
        source_id="fixture_derived",
        source_type="derived",
        source_url="https://example.invalid/derivation",
        title="Fixture derived timings",
        retrieved_at=TODAY,
    ),
    Source(
        source_id="fixture_stale_operator",
        source_type="official",
        source_url="https://example.invalid/operator/old",
        title="Fixture superseded operator page",
        retrieved_at=dt.date(2023, 5, 1),
        authoritative_until=dt.date(2024, 1, 1),
    ),
]

SYNTHETIC_STOPS = {
    "ALM_0001": ("Fixture Centro", 36.7350, -3.6890),
    "ALM_0002": ("Fixture Playa", 36.7300, -3.6950),
    "ALM_0003": ("Fixture Cruce", 36.7280, -3.7050),
    "ALM_0004": ("Fixture Herradura", 36.7290, -3.7350),
}

#: Densified so that geometry checks see a realistic point spacing.
SYNTHETIC_SHAPE_POINTS = [
    (36.7350, -3.6890),
    (36.7332, -3.6912),
    (36.7315, -3.6934),
    (36.7300, -3.6950),
    (36.7294, -3.6985),
    (36.7288, -3.7020),
    (36.7280, -3.7050),
    (36.7282, -3.7120),
    (36.7285, -3.7190),
    (36.7287, -3.7265),
    (36.7290, -3.7350),
]


def observation(entity: str, field: str, value: str, **kwargs) -> Observation:
    kwargs.setdefault("source_id", "fixture_operator")
    kwargs.setdefault("retrieved_at", TODAY)
    kwargs.setdefault("confidence", Confidence.CONFIRMED)
    return Observation(entity=entity, field=field, value=value, **kwargs)


def fixture_observations() -> list[Observation]:
    rows: list[Observation] = [
        observation("agency:ALM", "agency_name", "Fixture Urban Buses"),
        observation("agency:ALM", "agency_url", "https://example.invalid/operator"),
        observation("route:ALM_9", "route_short_name", "9"),
        observation("route:ALM_9", "route_long_name", "Fixture Centro - Fixture Herradura"),
        observation("route:ALM_9", "seasons", "summer;winter"),
        observation("service:ALLYEAR_WD", "weekdays", "mon;tue;wed;thu;fri"),
        observation("service:ALLYEAR_WD", "start_date", SEASON_START.isoformat()),
        observation("service:ALLYEAR_WD", "end_date", SEASON_END.isoformat()),
        observation("service:ALLYEAR_WD", "description", "Fixture weekday service"),
        observation("shape:ALM_9_OUT", "geometry", "geometry/ALM_9_OUT.geojson"),
    ]

    for stop_id, (name, latitude, longitude) in SYNTHETIC_STOPS.items():
        entity = f"stop:{stop_id}"
        rows.append(observation(entity, "name", name))
        rows.append(
            observation(
                entity,
                "coordinate",
                f"{latitude},{longitude}",
                source_id="fixture_ibus",
                evidence_kind=EvidenceKind.STOP_COORDINATE,
                confidence=Confidence.HIGH,
            )
        )
        rows.append(observation(entity, "municipality", "Almuñécar"))

    sequence = ";".join(SYNTHETIC_STOPS)
    rows += [
        observation("pattern:ALM_9_OUT", "route_id", "ALM_9"),
        observation("pattern:ALM_9_OUT", "direction_id", "0"),
        observation("pattern:ALM_9_OUT", "season", "all_year"),
        observation("pattern:ALM_9_OUT", "headsign", "Fixture Herradura"),
        observation("pattern:ALM_9_OUT", "stop_sequence", sequence),
        observation(
            "pattern:ALM_9_OUT",
            "offsets",
            "0;240;480;900",
            source_id="fixture_derived",
            confidence=Confidence.MEDIUM,
            derivation="Median offset across recorded runs; endpoints from the timetable.",
            derived_from="fixture_operator;fixture_ibus",
            sample_size=7,
        ),
        observation(
            "pattern:ALM_9_OUT",
            "timing_methods",
            "published;observed_median;observed_median;published",
        ),
        observation("pattern:ALM_9_OUT", "shape_id", "ALM_9_OUT"),
        observation("pattern:ALM_9_OUT", "departures:ALLYEAR_WD", "07:30;08:30;09:30"),
    ]
    return rows


@pytest.fixture
def evidence() -> EvidenceStore:
    return EvidenceStore(sources=FIXTURE_SOURCES, observations=fixture_observations())


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A throwaway ``data/`` tree containing the fixture shape geometry."""
    geometry_dir = tmp_path / "evidence" / "geometry"
    geometry_dir.mkdir(parents=True)
    (geometry_dir / "ALM_9_OUT.geojson").write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lon, lat] for lat, lon in SYNTHETIC_SHAPE_POINTS],
                },
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def network(evidence: EvidenceStore, data_dir: Path):
    from almunecar_gtfs.reconcile import reconcile

    result = reconcile(evidence, data_dir)
    assert result.problems == [], result.problems
    return result.network
