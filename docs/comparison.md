# Cross-checks against independent sources

*Generated 2026-08-10 by `almunecar-gtfs compare`. Do not edit by hand.*

Neither source below can overrule the canonical dataset. Both exist to make
disagreements visible. A row that agrees is evidence; a row that does not is a
question for a human.

## Moovit

Transcribed from Moovit in a browser on 2026-08-10; Moovit renders
its pages with JavaScript and serves nothing to a plain HTTP client.

| Pattern | Moovit line | Our stops | Moovit stops | Verdict |
|---|---|---:|---:|---|
| `ALM_1_CIRC` | LÍNEA 1 (Circular) | 19 | 21 | stop counts differ by 2 |
| `ALM_2B_CIRC_SUMMER` | LÍNEA 2 LA HERRADURA (Almuñécar - La Herradura - Marina del Este) | 24 | 23 | stop counts differ by 1 |
| `ALM_3A_CIRC` | LÍNEA 3 (Velilla) | 22 | 22 | stop counts agree |
| `ALM_TORRECUEVAS_CIRC` | LÍNEA 5 (Torrecuevas) | 17 | 17 | stop counts agree |

### Notes

- **LÍNEA 1** — Still lists Paseo Del Altillo, which is closed to traffic since 2026-04-13.
- **LÍNEA 2 LA HERRADURA** — Moovit models 2A and 2B as one line. Its listed hours (Mon-Fri 07:35-20:30) are the operator's *winter* times, read during summer, so Moovit appears to be a season behind.
- **LÍNEA 3** — Moovit shows a single 'Línea 3'; the operator splits it into 3A, 3B and 3C.
- **LÍNEA 5** — Third source calling Torrecuevas line 5. Not independent of OSM or of the operator's winter page: all three could be reading the same signage.

Moovit's first and last departures are recorded too:

| Moovit line | First | Last | Stated duration |
|---|---|---|---|
| LÍNEA 1 | — | — | 19 min |
| LÍNEA 2 LA HERRADURA | 07:35 | 20:30 | 33 min |
| LÍNEA 3 | 07:40 | 20:30 | 20 min |
| LÍNEA 5 | 09:00 | 19:15 | 18 min |

Moovit's stated trip durations are the only end-to-end journey times any source
gives. They are **not** used to synthesise stop times: one number for a whole
loop cannot be apportioned between stops without inventing the apportionment,
and Moovit is a QA reference, not an authority on the operator's timetable.

## The operator's own route diagrams

Transcribed from the diagram images on the operator's pages. These use the
operator's stop names, which do not match OpenStreetMap's, so only counts and
endpoints can be compared mechanically; the names themselves are listed in
`sources/official.py` for manual review.

| Pattern | Diagram | Our stops | Diagram stops | Verdict |
|---|---|---:|---:|---|
| `ALM_2A_CIRC` | ALM_2A operator diagram | 20 | 22 | stop counts differ by 2 |
| `ALM_2B_CIRC_SUMMER` | ALM_2B operator diagram | 24 | 29 | stop counts differ by 5 |
| `ALM_2B_CIRC_WINTER` | ALM_2B operator diagram | 23 | 29 | stop counts differ by 6 |
| `(none for ALM_3B)` | ALM_3B operator diagram | 0 | 37 | no reconstructed pattern to compare against |
| `ALM_TORRECUEVAS_CIRC` | ALM_TORRECUEVAS operator diagram | 17 | 25 | stop counts differ by 8 |
