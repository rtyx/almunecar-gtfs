# Methodology

## The two questions

This repository keeps two answers apart, permanently:

1. **What do the available sources say?** — `data/evidence/`
2. **What do we believe the canonical network actually is?** — `data/canonical/`

Reconciliation reads (1) and writes (2). It never edits (1). This matters because
the second answer is a judgement that will be revisited: when a timetable changes
or a new source appears, a reviewer needs to see what was known and what was
decided, not just the current conclusion.

## Pipeline

| Stage | Input | Output | Code |
|---|---|---|---|
| Acquisition | operator/municipal/iBusGPS/Moovit/OSM | `observations.csv` | `sources/` |
| Reconciliation | observations | `data/canonical/`, `conflicts.yaml` | `reconcile/` |
| Generation | canonical | `data/generated/` | `gtfs/build.py` |
| QA | canonical | findings | `qa.py` |
| Validation | zip | validator report | `gtfs/validate.py` |

Scrapers may not write canonical data. Nothing may hand-edit generated GTFS.
Canonical files are generated but committed, so `git diff` shows exactly how a
belief about the network changed — and CI re-runs reconciliation and fails if the
committed canonical data does not reproduce.

## The observation

Every non-trivial transit fact is an observation:

    entity, field, value, source_id, retrieved_at, confidence,
    evidence_kind, source_url, derivation, derived_from, sample_size, notes

`entity` is namespaced: `route:ALM_2B`, `stop:ALM_0001`, `pattern:ALM_2B_OUT_SUMMER`,
`service:SUMMER_WD`, `shape:ALM_2B_OUT`, `agency:ALM`.

`value` is always text. The field registry in `reconcile/fields.py` says how each
field is typed, which keeps the evidence file a plain, diffable CSV while making
a typo in a field name an error rather than a silently ignored row.

Confidence is `confirmed | high | medium | low | unresolved`.

Latitude and longitude are a single `coordinate` field on purpose. Reconciling
them separately would let a stop end up with one source's latitude and another's
longitude — a position that no source ever claimed.

## Weighing evidence

Evidence is ranked **per field family**, not by choosing one source globally.
The ordering key, best first:

1. Is the evidence disqualified for this domain? (a POI coordinate is)
2. Is the source marked stale? (`authoritative_until` in the past)
3. Position in the domain's hierarchy
4. Confidence
5. Recency
6. Source id, for a stable tie-break

Hierarchy outranks confidence deliberately. A medium-confidence operator page
beats a confirmed Moovit page, because the operator is the authority on its own
network and Moovit is a third party reading the same signs we are.

### Disqualified evidence

> Never use an ordinary POI coordinate as evidence for a stop without additional
> confirmation.

A hotel called *Playa Velilla* is not the bus stop called *Playa Velilla*. Any
observation tagged `evidence_kind: poi` is disqualified in the `stop_coord`
domain and cannot establish a coordinate on its own. It is rescued only if a
*different* source independently places the stop within 30 m — and the result is
then downgraded to `low` confidence. A stop with no other evidence produces a
reconciliation problem and is left out, rather than being invented.

## Conflicts

Any `(entity, field)` where registered sources state different values becomes a
`Conflict`, with every claim preserved. Resolution is a human act recorded in
`conflicts.yaml`; regeneration merges rather than overwrites:

- a human resolution survives regeneration;
- a resolved conflict **reopens** if the underlying claims change;
- a conflict that stops reproducing is marked `accepted_ambiguity`, never deleted;
- `blocks_publication: true` keeps the affected entity out of the feed until settled.

## Stops

One record per **physical boarding location**, with a stable id (`ALM_0001`) that
is never derived from the name, so renaming a stop does not renumber the dataset.

Two poles facing each other across a road are two stops. They are linked by
`pair_stop_id` and distinguished by `direction_hint`, not merged.

The QA suite flags, for human review rather than automatic correction:

- same name more than 100 m apart;
- distinct ids closer than 10 m;
- anything outside the service-area bounding box;
- a `pair_stop_id` that is missing or not reciprocal.

## Patterns, not just routes

A route is what a passenger calls the service. A **pattern** is an ordered stop
sequence that is actually operated: `2A` outbound, `2B` inbound, and the summer
`3B` Cabria extension are three patterns. Conditional behaviour — a port served
on some trips only — is stated in `conditional` and given its own
`variant_code`, so that generated trip ids stay stable and nothing pretends every
trip serves every stop.

## Timings

The operator publishes departures from the principal stop; GTFS needs a time at
every stop. The resolution:

- the origin departure is exact — `timepoint=1`;
- other stops carry an offset in seconds with an explicit `timing_method`:
  `published` (`timepoint=1`), `observed_median` or `interpolated`
  (`timepoint=0`), or `unknown`;
- the derivation is recorded per pattern: method, description, sample size,
  and the source ids it consumed;
- offsets derived from observed runs use a **median across several runs**, never
  a single trip — one delayed bus is not a timetable;
- a pattern with any unknown offset is `not_publishable` and is excluded from the
  build. The build refuses to emit a feed with no publishable trips rather than
  shipping an empty one.

### Unblocking `stop_times.txt`

This is the project's hard problem, so it gets its own plan rather than a hope.

GTFS is asymmetric about times, and the asymmetry is what makes this tractable:

| Position in trip | GTFS requirement | What we may do |
|---|---|---|
| First stop | `arrival_time` / `departure_time` **required** | must be a published time |
| Intermediate stops | conditionally required; `timepoint=0` marks an approximation | may be estimated, if it says so |
| Last stop | `arrival_time` / `departure_time` **required** | must be a published time |

So an estimated middle is legitimate and honest. An estimated *end* is not an
approximation at all — it is the feed asserting when the service starts and
finishes, and every downstream trip planner will treat it as fact. The code
enforces exactly that split: `Pattern.has_anchored_endpoints` requires the first
and last calls to be `published`, `is_publishable` requires it, and the builder
drops any pattern that fails it.

Every line here is a circular that starts and ends at the same stop, so the
missing anchor is a single number per pattern: **the loop running time**. With it,
the intermediates follow by distance-proportional allocation along the shape,
marked `timepoint=0` with `method: interpolated`. Without it, nothing ships.

Ranked ways to get that number, best first:

1. **Ask the operator.** They dispatch to it. One email settles every pattern at
   `confirmed`, and it is also the conversation that has to happen anyway about
   publication rights.
2. **Recorded vehicle runs.** A handful of GPS traces of each loop, or simply
   riding it with a phone. Take the **median across several runs**, never a single
   trip — one bus stuck behind a delivery van is not a timetable. This also yields
   real per-stop offsets rather than a modelled allocation, upgrading the middles
   from `interpolated` to `observed_median`.
3. **iBusGPS, if it is ever located.** Vehicle positions over a day give the same
   thing automatically, and are the prerequisite for realtime anyway.
4. **Headway inference.** Where consecutive departures are 30 minutes apart and a
   single vehicle works the line, the loop must fit inside 30 minutes. That is an
   upper bound, not a duration, and bounds do not belong in `stop_times.txt`.
5. **Moovit's stated durations** (18–33 minutes per loop). Recorded in
   `docs/comparison.md` and deliberately unused: Moovit is a QA reference, its data
   is currently a season out of date, and one number for a whole loop cannot be
   apportioned between stops without inventing the apportionment.

Options 1 and 2 are the real ones. Until one of them lands, the honest output is
no feed, which is what the pipeline produces.

## Geometry

`shapes.txt` is generated even though GTFS tolerates its absence, because a feed
without geometry draws straight lines through the sea between Almuñécar and
La Herradura.

Shape geometry lives in `data/evidence/geometry/*.geojson`, referenced from an
observation so it keeps its provenance. QA flags a shape that jumps more than
300 m between consecutive points (too coarse) or 1.5 km (broken), and a stop more
than 50 m from its own shape.

## Seasons

Two published periods — summer (1 July – 15 September) and winter (16 September –
30 June) — modelled with `calendar.txt`, with `calendar_dates.txt` for exceptions.
Special sub-periods, such as a summer extension running only part of the season,
are separate service/pattern combinations rather than a note in the README.

QA checks that the feed covers at least 28 days into the future (Google's
requirement) and reports any date inside that horizon with no service at all,
which is how an accidental gap at a season boundary shows up.
