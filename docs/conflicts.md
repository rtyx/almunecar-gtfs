# Source conflicts

*Generated 2026-08-10 by `almunecar-gtfs conflicts`. Do not edit by hand —
record decisions in `data/evidence/conflicts.yaml` and regenerate.*

2 recorded conflict(s): 1 unresolved, 1 blocking publication.

Conflicting source data is never discarded. A resolved row still shows every
claim that was rejected, so a future reviewer can re-examine the decision
instead of re-doing the research.

| Entity | Field | official | municipal | ibusgps | moovit | osm | field | derived | Resolution |
|---|---|---|---|---|---|---|---|---|---|
| `route:ALM_TORRECUEVAS` | route_short_name | `4` (official_torrecuevas_summer)<br>`5` (official_torrecuevas_winter) | — | — | — | `5` (osm_route_relations) | — | — | unresolved ⛔ blocks publication — Not resolvable from the sources available on 2026-08-10, and deliberately not guessed. The two operator pages carry the same sitemap lastmod (2026-05-14), so neither is simply the older one; OSM independently says 'Línea 5' but is a third-party reading of the same signage. The summer page is demonstrably careless (its own validity sentence says "horario de invierno" for 1 July to 15 September), which weakens '4' without establishing '5'. Settle by asking the operator, or by photographing the line number on the vehicle and at Plaza de la Carrera. Until then the route is excluded from the feed rather than published under a number that may be wrong. |
| `pattern:ALM_TORRECUEVAS_CIRC` | stop_sequence | `ALM_0001;ALM_0072;ALM_0069;ALM_0060;ALM_0065;ALM_0061;ALM_0062;ALM_0063;ALM_0073;ALM_0064;ALM_0074;ALM_0066;ALM_0067;ALM_0068;ALM_0070;ALM_0071;ALM_0001` (official_torrecuevas_summer) | — | — | — | `ALM_0001;ALM_0060;ALM_0061;ALM_0062;ALM_0063;ALM_0064;ALM_0065;ALM_0066;ALM_0067;ALM_0068;ALM_0069;ALM_0070;ALM_0071;ALM_0072;ALM_0073;ALM_0074;ALM_0001` (osm_route_relations) | — | — | **ALM_0001;ALM_0072;ALM_0069;ALM_0060;ALM_0065;ALM_0061;ALM_0062;ALM_0063;ALM_0073;ALM_0064;ALM_0074;ALM_0066;ALM_0067;ALM_0068;ALM_0070;ALM_0071;ALM_0001** — Resolved in favour of the operator's route diagram. OpenStreetMap relation 18501914 lists the same platforms but not in travel order: it places Cortijo Cahicillos, the far apex of the line, between two stops beside the town. The geometry check settles it rather than the hierarchy alone — honouring OSM's order forces Cortijo Cahicillos to a point 3,471 m from where it actually sits, and Torrecuevas to one 2,432 m away, while both are within 10 m of the route. The operator's order produces no such contradiction. OSM's claim is kept here because the upstream relation should be fixed, not just worked around. |

## Unresolved detail

### `route:ALM_TORRECUEVAS` — route_short_name

**Blocks publication.** The affected entity is excluded from the feed until this is settled.

- `4` — Línea Torrecuevas verano (https://urbanosalmunecar.es/lineas-urbanas-almunecar/torrecuevas-verano/), retrieved 2026-08-10, confidence high. Page body heading reads 'LINEA 4 TORRECUEVAS'. The same page's validity sentence wrongly says 'horario de invierno' for 1 July to 15 September, so the page is not carefully maintained.
- `5` — Línea 5 Torrecuevas invierno (https://urbanosalmunecar.es/lineas-urbanas-almunecar/torrecuevas-linea-5-invierno/), retrieved 2026-08-10, confidence high. Page title reads 'Línea 5 Torrecuevas invierno' and the URL slug contains 'linea-5'. Same sitemap lastmod as the summer page (2026-05-14), so neither can be dismissed as simply older.
- `5` — OpenStreetMap bus route relations for Grupo Fajardo, via Overpass (https://overpass-api.de/api/interpreter), retrieved 2026-08-10, confidence medium. OSM relation ref='Línea 5', operator='Grupo Fajardo'.
