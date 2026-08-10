# almunecar-gtfs

Source-backed GTFS Schedule and transit data for the Almuñécar urban bus network.

> **This is an unofficial dataset.** It is not published by, endorsed by, or
> affiliated with Autocares Urbanos Almuñécar / Roalfa. Nothing here may be
> presented as an official operator feed unless and until the operator
> authorises it — see [`docs/google-transit-submission.md`](docs/google-transit-submission.md).

## What this repository is

A defensible, maintainable representation of Almuñécar's public bus network —
not a script that manufactures a valid ZIP. It answers two questions separately
and never lets the second destroy the first:

1. **What do the available sources say?** → `data/evidence/`
2. **What do we believe the canonical network actually is?** → `data/canonical/`

GTFS is generated deterministically from the canonical dataset. Generated files
are never hand-edited.

```
sources          reconciliation        canonical            GTFS
 official  ─┐                       ┌─ stops.geojson  ─┐
 municipal ─┤    observations.csv   ├─ routes.yaml     ├─ data/generated/
 iBusGPS   ─┼──▶ conflicts.yaml ───▶┼─ patterns.yaml   ┼─▶ almunecar-gtfs.zip
 Moovit    ─┤                       ├─ schedules.yaml  ┤
 OSM       ─┘                       └─ shapes.geojson ─┘
```

## Current data coverage

**None yet.** The pipeline, models, QA suite and CI are in place; source
acquisition (plan tasks 3–8) has not been completed, so `data/evidence/` holds
only its headers and no feed can be built. Coverage will be reported here, per
route and season, as evidence lands.

Routes to be researched and verified, summer and winter separately:

| Line | Service | Status |
|------|---------|--------|
| 1 | Circular | not yet researched |
| 2A | Almuñécar – La Herradura | not yet researched |
| 2B | Almuñécar – La Herradura – Punta de la Mona | not yet researched |
| 3A | Velilla – Taramay | not yet researched |
| 3B | Velilla (summer) | not yet researched |
| 3C | Taramay (summer) | not yet researched |
| 4 | Torrecuevas | not yet researched — **numbering disputed**, see below |

## Known uncertainties

- **Torrecuevas line number.** A winter operator page identifies the service as
  line 5; more recent operator material calls it line 4. Both claims are to be
  recorded with dates and the current designation established from evidence, not
  intuition. Until then the conflict is registered and blocks publication of
  that route.
- **Intermediate stop times.** The operator appears to publish departures from
  the principal stop rather than a time at every stop. GTFS needs
  `stop_times.txt` regardless. Origin departures are marked `timepoint=1`;
  anything derived is marked `timepoint=0` and records how it was derived. A
  route whose timings cannot be established with reasonable confidence is
  flagged `not_publishable` rather than fabricated.
- **Line 2B and Puerto Marina del Este.** Whether the port is always served is
  an open question — alternate pattern, operational exception, or realtime alert.
- **Temporary diversions** (construction, seasonal extensions such as the 3B
  Cabria extension) still need to be inventoried.

Every unresolved disagreement is in [`docs/conflicts.md`](docs/conflicts.md),
generated from `data/evidence/conflicts.yaml`.

**Last source verification:** not yet performed.

## Source methodology

Evidence is weighed **per field**, not by picking one global winner. Summarised:

| Field family | Hierarchy (best first) |
|---|---|
| Route names, service periods, departures | operator → municipal → iBusGPS → Moovit → OSM |
| Stop coordinates | explicit operator/iBusGPS platform coordinate → official map pin → municipal GIS → verified OSM `highway=bus_stop` → Moovit → manual research |
| Route geometry | operator/iBusGPS data or vehicle traces → municipal geometry → OSM roads → reconstruction from stop sequence |

Rules the code enforces rather than merely documents:

- Hierarchy position beats confidence — a medium-confidence operator page
  outranks a confirmed Moovit page.
- A page marked `authoritative_until` in the past loses to a current one, so an
  old route number can never win by default.
- An ordinary POI coordinate is **disqualified** as stop evidence unless an
  independent source confirms the same position; if it is, the result is
  downgraded to low confidence.
- Physical stops stay separate even with identical names. Opposite sides of a
  road are different `stop_id`s.
- Conflicting claims are preserved after reconciliation, and a resolved conflict
  reopens automatically if the underlying claims change.

Full detail: [`docs/methodology.md`](docs/methodology.md).

## Rebuilding the feed

```bash
uv sync
```

```bash
uv run almunecar-gtfs reconcile
```

```bash
uv run almunecar-gtfs check
```

```bash
uv run almunecar-gtfs build
```

Outputs land in `data/generated/gtfs/*.txt` and `data/generated/almunecar-gtfs.zip`.
The build is deterministic: identical canonical input produces a byte-identical
zip, so a diff in the artifact always means a diff in the data.

Other commands:

```bash
uv run almunecar-gtfs map
```

```bash
uv run almunecar-gtfs conflicts
```

```bash
uv run almunecar-gtfs monitor
```

## Validating

The MobilityData Canonical GTFS Schedule Validator is never downloaded
automatically. Obtain a copy from
[its releases page](https://github.com/MobilityData/gtfs-validator/releases),
then:

```bash
GTFS_VALIDATOR_JAR=/path/to/gtfs-validator-cli.jar uv run almunecar-gtfs validate
```

CI fetches the jar explicitly in `.github/workflows/validate-gtfs.yml`, fails on
any validator **error**, and keeps warnings as a downloadable artifact.
The release criterion is zero errors; suppressing an error to get a green build
defeats the point.

## Development

```bash
uv run pytest
```

```bash
uv run ruff check .
```

Both run on every push and pull request.

## Repository layout

| Path | Contents |
|---|---|
| `data/evidence/` | What sources say: `sources.yaml`, `observations.csv`, `conflicts.yaml`, `geometry/` |
| `data/canonical/` | What we believe: generated by `reconcile`, committed so changes are reviewable |
| `data/generated/` | GTFS output (git-ignored; rebuilt from canonical data) |
| `src/almunecar_gtfs/sources/` | Acquisition. Writes observations only |
| `src/almunecar_gtfs/reconcile/` | The only code allowed to produce canonical data |
| `src/almunecar_gtfs/gtfs/` | Deterministic GTFS generation and validator wrapper |
| `src/almunecar_gtfs/qa.py` | Invariant checks, shared by the CLI, CI and tests |
| `qa/` | Local review artifacts: QA map, validation reports (git-ignored) |
| `docs/` | Methodology, sources, conflicts, Google Transit handoff |

## Licensing

Code is one thing; transit data is another. The code in `src/` and `tests/` is
covered by this repository's licence. The *data* in `data/` is compiled from
third-party sources whose republication rights are not yet established — that
question is open and is tracked in `docs/google-transit-submission.md`. No
copyrighted timetable images or scraped site assets are committed; the
repository stores extracted facts, URLs, retrieval dates and content hashes.
