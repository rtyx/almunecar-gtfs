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

Source research is done for the operator's whole published network; the dataset
reconciles cleanly and passes every QA invariant. **No GTFS feed can be built
yet**, for one reason, stated up front:

> The operator publishes only the departure time from the principal stop —
> every page says so: *"LOS HORARIOS INDICAN LA HORA DE SALIDA DESDE LA PARADA
> PRINCIPAL"*. GTFS requires a time at every stop. No source found so far gives
> one, and no observed vehicle runs are available to derive one. Rather than
> invent them, every pattern is marked `not_publishable` and
> `almunecar-gtfs check` names the blocker per pattern.

What is in the dataset today, all with provenance:

| | Count |
|---|---|
| Physical stops with coordinates | 74 |
| Routes | 7 |
| Route patterns with ordered stop sequences | 6 |
| Origin departures transcribed from operator timetables | 116 |
| Route shapes from real road geometry | 5 |
| Recorded source conflicts | 1 (blocking) |

| Line | Service | Sequence | Timetable | Publishable |
|------|---------|----------|-----------|-------------|
| 1 | Circular | ✅ OSM | ✅ summer + winter | ❌ roadworks diversion not in geometry |
| 2A | Almuñécar – La Herradura | ✅ OSM | ✅ summer + winter | ❌ no intermediate timings |
| 2B | …– Punta de la Mona | ✅ OSM, summer and winter variants | ✅ summer + winter | ❌ no intermediate timings |
| 3A | Velilla – Taramay | ✅ OSM | ✅ summer + winter | ❌ no intermediate timings |
| 3B | Velilla (summer only) | ❌ not mapped | ⚠️ Sundays only; weekdays published as a frequency | ❌ no stop sequence |
| 3C | Taramay (summer only) | ❌ not mapped | ✅ summer | ❌ no stop sequence |
| 4 / 5 | Torrecuevas | ✅ OSM | ✅ summer + winter | ❌ line number disputed |

**Last source verification: 2026-08-10.**

## Known uncertainties

- **The Torrecuevas line number is unresolved and blocks publication of that
  route.** The operator's summer page body says `LINEA 4 TORRECUEVAS`; its winter
  page title and URL say `Línea 5`; OpenStreetMap independently says `Línea 5`.
  Both operator pages carry the *same* sitemap `lastmod` (2026-05-14), so neither
  is simply the older one, and the summer page is demonstrably careless — its own
  validity sentence reads "horario de **invierno** desde el 1 julio". Settle it by
  asking the operator or photographing the vehicle, not by guessing.
- **Intermediate stop times do not exist in any source.** See above. This is the
  single thing standing between this dataset and a publishable feed.
- **Line 2B and Puerto Marina del Este: resolved.** The operator's 2B route
  diagram marks `MARINA DEL ESTE*` and the winter page footnotes it: *"Esta parada
  no se realiza en el horario de invierno."* So it is a **seasonal pattern
  difference**, not an operational exception and not a realtime alert. The winter
  pattern `ALM_2B_CIRC_WINTER` omits that stop. What remains unclear is the summer
  timetable's split into an unmarked row and a `* BAJADA PUERTO` row — which of
  the two actually descends to the port is not stated anywhere.
- **Temporary diversion, active now.** From 13 April 2026 the Paseo del Altillo is
  closed for roadworks on the Paseo de la Caletilla, estimated ten months, and the
  urban lines divert via calle Guadix. The available geometry does not reflect
  this, which is why line 1 is held back.
- **3B Cabria extension, confirmed.** From 17 July to 15 September, line 3B runs
  on to a new stop at the Avda. Pintor Domínguez de Haro roundabout by Playa de
  Cabria. The operator links a map pin for it; that pin sits noticeably inland of
  the beach and needs checking before use.
- **Feria de San José.** Between 16 and 22 March, line 2B runs the 2A itinerary.
- **3B weekday service is a frequency, not a list** ("cada 30 min desde las 8:30
  hasta 14:30 y desde 17:00 hasta 0:30"). Expanding that into departures is an
  interpretation, so it is recorded as prose rather than as published times.
- **iBusGPS was looked for and not found.** Nothing on the operator's site or on
  grupofajardo.es links to a public realtime endpoint as of 2026-08-10.
- **Public holidays are not modelled.** Sunday and holiday timetables are shared,
  but the operator does not publish which days are holidays.

- **OpenStreetMap's Torrecuevas route is missing stops.** The operator's own
  diagram lists 25 calls (including Cementerio, Eucalipto and Cahicillos 1/2);
  OSM and Moovit both list 17. Since the sequence comes from OSM, the pattern is
  very likely incomplete — another reason that route is held back.

Every unresolved disagreement is in [`docs/conflicts.md`](docs/conflicts.md),
generated from `data/evidence/conflicts.yaml`. Cross-checks against Moovit and
against the operator's own route diagrams are in
[`docs/comparison.md`](docs/comparison.md).

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
uv run almunecar-gtfs ingest --offline
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

`build` currently refuses, because no pattern is publishable — see *Current data
coverage*. Once timings exist, outputs land in `data/generated/gtfs/*.txt` and
`data/generated/almunecar-gtfs.zip`. The build is deterministic: identical
canonical input produces a byte-identical zip, so a diff in the artifact always
means a diff in the data.

`ingest --offline` rebuilds the evidence files from the committed OSM extract and
the transcribed operator timetables without touching the network. Drop
`--offline` to re-fetch the operator pages and refresh their content hashes.

Other commands:

```bash
uv run almunecar-gtfs map
```

```bash
uv run almunecar-gtfs conflicts
```

```bash
uv run almunecar-gtfs compare
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
| `data/evidence/` | What sources say: `sources.yaml`, `observations.csv`, `conflicts.yaml`, `stop_registry.yaml`, `geometry/`, `osm/` |
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

The operator's timetables are published as images. Those images are **not**
committed; they are fetched into the git-ignored `data/cache/` and the departure
times were transcribed from them by hand, each recording the image URL it came
from. Stop coordinates, stop sequences and route geometry come from
OpenStreetMap — © OpenStreetMap contributors, ODbL — and the Overpass extract
they were derived from is committed under `data/evidence/osm/`.
