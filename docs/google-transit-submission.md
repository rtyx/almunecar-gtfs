# Google Transit handoff

## Status

**Not ready, and not for us to submit.** Google Transit accepts feeds from the
transit agency or an authorised data provider. This project is neither. The
correct outcome is that Roalfa / Autocares Urbanos Almuñécar owns the feed and
this repository supplies the engineering.

Do not create a Google Transit Partner account representing the operator, and do
not describe this dataset as an official feed, unless the operator has said yes.

## What GTFS is, in one paragraph (for the operator)

GTFS is the standard file format journey planners read. It is a zip of plain
tables: the stops, the routes, when each trip runs, and the path each route
takes. Google Maps, Apple Maps, Moovit and open journey planners all consume it.
Without one, Almuñécar's buses are invisible in the apps most visitors use;
with one, a passenger searching "Almuñécar to La Herradura" sees the bus.

## What already exists

- A structured, validated GTFS Schedule feed built from documented sources.
- A written record of where every fact came from, and of the disagreements
  between sources that had to be settled.
- Automatic checks: geometry sanity, calendar coverage, and the MobilityData
  canonical validator, with a zero-error release criterion.
- Weekly monitoring of the operator's pages, so a timetable change raises an
  issue instead of quietly rotting.

## What the operator would need to do

1. **Confirm the data.** Review the routes, stops and timetables and say what is
   wrong. Nothing here is authoritative until they have.
2. **Decide ownership and licensing.** Who publishes the feed, and under what
   terms may others use it.
3. **Register with Google.** Google Transit Partner Dashboard, in the operator's
   name.
4. **Point Google at a stable URL.** See below.

## Hosting

```
stable HTTPS URL
        ↓
almunecar-gtfs.zip
        ↓
Google Transit Partner Dashboard
```

The URL must stay the same across updates. Google re-fetches it; a URL that
changes per release breaks the integration.

**No dates or version numbers in the public feed URL.** Version metadata belongs
in `feed_info.txt`, where `feed_version` carries the latest source-verification
date.

## Realtime, later

iBusGPS may expose vehicle positions. If it does, a GTFS-Realtime
`VehiclePosition` feed is the natural next step, referencing the same ids as the
static feed. `TripUpdate` and `ServiceAlert` come after that, and predictions
only once vehicle-to-trip matching is reliable. This is deliberately a separate
phase: static GTFS has to be correct first.

## MobilityDatabase

Once publication rights and hosting are settled, the feed should also be listed
in MobilityDatabase — independent validation, an open catalogue entry, and
discoverability by journey planners other than Google. Not before: listing a feed
whose licensing is unresolved creates a problem for everyone who reuses it.

## Definition of "Google-ready"

A validating ZIP is **not** sufficient. All of the following must hold:

- [ ] static GTFS validates with zero errors
- [ ] service covers at least four weeks into the future
- [ ] operator identity and data-publication authority are resolved
- [ ] a stable hosted feed URL exists
- [ ] Roalfa / Grupo Fajardo has authorised the Google Transit integration
- [ ] the feed can be entered into the Google Transit Partner workflow
