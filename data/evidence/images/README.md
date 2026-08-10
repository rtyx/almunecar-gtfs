# Operator timetable and route-diagram images

Autocares Urbanos Almuñécar publishes every timetable and route diagram as an
image. There is no markup to parse, so each departure time in
`src/almunecar_gtfs/sources/official.py` was **read off one of these pictures by
hand** on 2026-08-10.

They are committed here so that the transcription can be checked. Open the image
next to the code and you can see for yourself whether `9:00 - 10:00 - 12:00` was
copied correctly — which is the whole point of a provenance-first dataset. They
also serve as an archive: the operator has already reorganised these pages once,
and `monitor-sources` can tell us a page *changed* but cannot show us what it
used to say.

## Provenance

`../images.yaml` records, for every file: its SHA-256, its byte size, the
operator page it came from, the exact upload URL, what it depicts, and whether it
is a timetable, a route diagram, a street map or an operational notice.
`almunecar-gtfs check` verifies the hashes, so an image cannot be swapped without
the transcription that cites it being flagged.

## Attribution and rights

These images are the work of **Autocares Urbanos Almuñécar / Grupo Fajardo** and
remain theirs. They are reproduced unmodified, with attribution and a link to the
source page, for verification and archival of a non-commercial open transit data
project. No claim of ownership is made and no licence is granted by this
repository.

The *facts* extracted from them — departure times, stop names, stop order — are
not themselves copyrightable and are what the dataset is actually built on.

If Autocares Urbanos Almuñécar / Grupo Fajardo would prefer these images not be
mirrored here, open an issue or contact the maintainer and they will be removed;
`almunecar-gtfs` can fall back to citing the URLs alone without losing any
transit data.
