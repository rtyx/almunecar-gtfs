# Almuñécar Urban Bus GTFS Implementation Plan

*Plan date: 2026-08-08. Execution started: 2026-08-09.*

**Goal:** Build a maintainable, source-backed GTFS dataset for the complete Almuñécar
urban bus network, suitable for validation, publication and eventual submission to
Google Transit / Google Maps.

**Repository:** `almunecar-gtfs` — Source-backed GTFS Schedule and transit data for the
Almuñécar urban bus network.

## Architecture

Do not hand-edit generated GTFS files. Maintain a canonical internal dataset containing
stops, route patterns, schedules, provenance and confidence information. Generate GTFS
from that dataset deterministically.

Separate:

1. source acquisition
2. source reconciliation
3. canonical transit data
4. GTFS generation
5. validation
6. optional realtime integration

## Tech stack

* Python 3.12+
* `uv` for dependency management
* Pydantic for canonical models
* httpx + BeautifulSoup for ordinary HTTP extraction
* Playwright only where JavaScript inspection is necessary
* GeoJSON for geographical source data
* pytest
* MobilityData Canonical GTFS Validator
* GitHub Actions
* optional Folium/Leaflet QA map

## Global constraints

* Never invent a stop, route, coordinate or timetable silently.
* Every non-trivial transit fact must have provenance.
* Preserve disagreements between sources until resolved.
* Keep physical bus stops separate even when their names are identical.
* A stop on the opposite side of the road is normally a different `stop_id`.
* Do not treat a hotel, restaurant or POI coordinate as a bus-stop coordinate merely
  because the stop shares its name.
* Prefer explicit bus-stop/platform coordinates.
* Keep Moovit as a secondary reference source.
* Do not make Moovit the authoritative source when it conflicts with current operator or
  municipal data.
* Treat current operator information as more authoritative than stale operator pages.
* Never silently infer that an older route number remains current.
* Do not commit copyrighted timetable images or scraped site assets unless permission is
  clear. Store extracted factual data, provenance, hashes and URLs instead.
* Do not claim that the feed is an official Roalfa feed unless Roalfa authorizes
  publication.
* Keep code licensing separate from transit-data licensing.
* Default the GitHub repository to private until data-publication rights are understood.

## Source hierarchy

Use evidence at field level rather than selecting one global source.

For route names, service periods and published departures:

1. Autocares Urbanos Almuñécar / Roalfa current website
2. Ayuntamiento de Almuñécar documents
3. iBusGPS
4. Moovit
5. OpenStreetMap

For stop coordinates:

1. explicit operator/iBusGPS stop coordinates
2. explicit official map pins
3. municipal GIS/documents
4. verified OpenStreetMap `highway=bus_stop` / `public_transport=platform`
5. Moovit
6. manually researched coordinates

For route geometry:

1. operator/iBusGPS route data or observed vehicle traces
2. municipal route geometry
3. verified OSM road geometry
4. reconstructed geometry from stop sequence

Never use an ordinary POI coordinate as evidence for a stop without additional
confirmation.

## Known starting network

Research and verify at minimum these current summer services:

* Line 1: Circular
* Line 2A: Almuñécar – La Herradura
* Line 2B: Almuñécar – La Herradura – Punta de la Mona
* Line 3A: Velilla – Taramay
* Line 3B: Velilla, summer only
* Line 3C: Taramay, summer only
* Line 4: Torrecuevas

Research the corresponding winter network separately.

Known discrepancy requiring explicit resolution:

* A Torrecuevas winter operator page identifies the service as Line 5.
* More recent operator material identifies Torrecuevas as Line 4.

Do not resolve this by intuition. Record both claims with dates and determine the
currently valid designation.

Also investigate current temporary deviations, including construction-related diversions
and seasonal extensions.

## Repository structure

```text
almunecar-gtfs/
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .github/workflows/{test.yml,validate-gtfs.yml,monitor-sources.yml}
├── docs/{methodology.md,sources.md,conflicts.md,google-transit-submission.md}
├── docs/superpowers/plans/2026-08-08-almunecar-gtfs.md
├── data/evidence/{sources.yaml,observations.csv,conflicts.yaml}
├── data/canonical/{agency.yaml,routes.yaml,stops.geojson,patterns.yaml,
│                   schedules.yaml,services.yaml,shapes.geojson}
├── data/generated/gtfs/
├── src/almunecar_gtfs/{models.py,provenance.py,dataset.py,cli.py}
├── src/almunecar_gtfs/sources/{official,municipal,ibusgps,moovit,osm}.py
├── src/almunecar_gtfs/reconcile/{stops,routes,patterns,schedules}.py
├── src/almunecar_gtfs/gtfs/{build,validate}.py
└── tests/test_{stops,routes,patterns,schedules,gtfs}.py
```

## Task list

| # | Task | Notes |
|---|------|-------|
| 1 | Repository and reproducible environment | `uv init`, deps, CI on every push and PR |
| 2 | Build the evidence model first | observations carry source, retrieval date, confidence; no scraper writes canonical data |
| 3 | Inventory every operator route | route matrix; summer/winter/weekday/Sat/Sun; unresolved disagreements to `conflicts.yaml` |
| 4 | Canonical physical stop registry | stable `ALM_nnnn` ids, coordinate provenance, automatic suspicion flags |
| 5 | Reconstruct stop sequences and route patterns | model patterns, not just routes; 2B Puerto Marina behaviour explicit |
| 6 | Determine actual route shapes | iBusGPS structured geometry first; never naive straight lines in production |
| 7 | Solve the timetable problem carefully | origin departures exact (`timepoint=1`), derived intermediates `timepoint=0`, method recorded |
| 8 | Model seasonal service | summer 1 Jul–15 Sep, winter 16 Sep–30 Jun; 3B Cabria extension 17 Jul–15 Sep |
| 9 | Generate GTFS Schedule | deterministic; stable ids; `route_type=3`, `Europe/Madrid`, `es` |
| 10 | Automated QA | stop/route/trip/calendar/geometry/provenance invariants |
| 11 | Canonical GTFS validator | CI fails on errors; warnings archived as artifact |
| 12 | Visual QA map | click `ALM_0042`, see why that coordinate was chosen |
| 13 | Discrepancy report | `docs/conflicts.md`; conflicting source data is never discarded |
| 14 | Moovit as explicit QA source | discrepancy detection, not dataset copying |
| 15 | iBusGPS as future GTFS-Realtime source | static feed first; no predictions before reliable trip matching |
| 16 | Publication artifacts | zip, validation report, GeoJSON, docs |
| 17 | Google Transit handoff | operator-owned publication; do not impersonate Roalfa |
| 18 | MobilityDatabase | only after publication status and provenance are clear |
| 19 | Source-change monitoring | scheduled hash diff opens an issue; never auto-overwrites canonical data |

## Definitions of done

**Research release** — all currently operating routes identified; summer and winter
variants documented; every route pattern has an ordered stop sequence; every physical stop
has coordinates; each coordinate has provenance; Moovit compared; official/operator
information compared; iBusGPS inspected; municipal evidence checked; remaining conflicts
explicitly documented.

**GTFS release** — `almunecar-gtfs.zip` builds reproducibly; required files present; all
trips have valid stop sequences; seasonal calendars modeled; estimated times marked;
shapes visually verified; canonical GTFS Validator reports zero errors; tests and CI pass;
provenance complete; known uncertainties documented.

**Google-ready** — *not* merely "the ZIP validates". Static GTFS validates; service covers
at least four weeks into the future; operator identity and data-publication authority are
resolved; a stable hosted feed URL exists; Roalfa/Grupo Fajardo has authorized the Google
Transit integration; the feed can be entered into the Google Transit Partner workflow.

## Important design principle

This repository answers two different questions separately:

> What do the available sources say?

and

> What do we believe the canonical network actually is?

Never destroy the first answer while constructing the second. The purpose of the project
is not to manufacture a valid ZIP. It is to create a defensible, maintainable
representation of Almuñécar's public bus network that can survive timetable changes,
seasonal services and conflicting source information.
