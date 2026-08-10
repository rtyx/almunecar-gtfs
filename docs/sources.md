# Sources

Registered sources live in `data/evidence/sources.yaml`; this document explains
what each kind is good for and how far to trust it.

## Hierarchies

**Route names, service periods, published departures**

1. Autocares Urbanos Almuñécar / Roalfa, current website
2. Ayuntamiento de Almuñécar documents
3. iBusGPS
4. Moovit
5. OpenStreetMap

**Stop coordinates**

1. explicit operator / iBusGPS stop coordinates
2. explicit official map pins
3. municipal GIS / documents
4. verified OSM `highway=bus_stop` / `public_transport=platform`
5. Moovit
6. manually researched coordinates

**Route geometry**

1. operator / iBusGPS route data or observed vehicle traces
2. municipal route geometry
3. verified OSM road geometry
4. reconstruction from the stop sequence

## Notes per source

**Operator (`official`).** Authoritative for its own network. Not automatically
current: seasonal pages linger for years. When a page is known to be superseded,
set `authoritative_until` so it can never outrank a newer page. A route number
found only on a stale page goes in `former_short_names`; it is never promoted.

**Municipal (`municipal`).** Ayuntamiento documents and GIS. Slower to change
than the operator site, and usually better for geometry and administrative
boundaries than for departure times.

**iBusGPS (`ibusgps`).** The passenger information system. Potentially the best
source for explicit stop coordinates and route geometry, and the eventual basis
for GTFS-Realtime. Inspect page source, bundles and XHR traffic; cache
everything; do not poll.

**Moovit (`moovit`).** A **QA reference, never an authority.** It is used to
detect discrepancies in route numbers, stop counts, stop order and first/last
departures. Its data is not copied into the canonical dataset, and a departure
time resting on Moovit raises a provenance warning. Moovit blocks automated
access; an honest dated manual transcription beats brittle scraping.

**OpenStreetMap (`osm`).** Low in the coordinate hierarchy but uniquely good at
distinguishing the two poles of a stop pair. Only `highway=bus_stop` and
`public_transport=platform` count as stop evidence — anything else with a
matching name is a POI, and a POI is not stop evidence.

**Field (`field`).** Direct observation: a photograph of a pole, a ridden trip, a
recorded GPS trace. Strong evidence, and the only way to settle some questions.

**Derived (`derived`).** Computed from other observations. Must record
`derivation`, `derived_from` and, for medians, `sample_size`. Ranks below every
real source, so it yields as soon as anyone actually publishes the fact.

## Fetching politely

`sources/base.py` sends a descriptive User-Agent with a contact route, waits at
least two seconds between requests to the same host, and caches every response
under `data/cache/` (git-ignored). Re-running extraction does not re-hit the
operator's site.

## What is committed

Extracted facts, URLs, retrieval dates and normalised content hashes. **Not**
timetable images, PDFs or scraped page assets — their republication rights are
not established.
