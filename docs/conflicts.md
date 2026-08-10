# Source conflicts

*Generated 2026-08-10 by `almunecar-gtfs conflicts`. Do not edit by hand —
record decisions in `data/evidence/conflicts.yaml` and regenerate.*

1 recorded conflict(s): 1 unresolved, 1 blocking publication.

Conflicting source data is never discarded. A resolved row still shows every
claim that was rejected, so a future reviewer can re-examine the decision
instead of re-doing the research.

| Entity | Field | official | municipal | ibusgps | moovit | osm | field | derived | Resolution |
|---|---|---|---|---|---|---|---|---|---|
| `route:ALM_TORRECUEVAS` | route_short_name | `4` (official_torrecuevas_summer)<br>`5` (official_torrecuevas_winter) | — | — | — | `5` (osm_route_relations) | — | — | unresolved ⛔ blocks publication — Not resolvable from the sources available on 2026-08-10, and deliberately not guessed. The two operator pages carry the same sitemap lastmod (2026-05-14), so neither is simply the older one; OSM independently says 'Línea 5' but is a third-party reading of the same signage. The summer page is demonstrably careless (its own validity sentence says "horario de invierno" for 1 July to 15 September), which weakens '4' without establishing '5'. Settle by asking the operator, or by photographing the line number on the vehicle and at Plaza de la Carrera. Until then the route is excluded from the feed rather than published under a number that may be wrong. |

## Unresolved detail

### `route:ALM_TORRECUEVAS` — route_short_name

**Blocks publication.** The affected entity is excluded from the feed until this is settled.

- `4` — Línea Torrecuevas verano (https://urbanosalmunecar.es/lineas-urbanas-almunecar/torrecuevas-verano/), retrieved 2026-08-10, confidence high. Page body heading reads 'LINEA 4 TORRECUEVAS'. The same page's validity sentence wrongly says 'horario de invierno' for 1 July to 15 September, so the page is not carefully maintained.
- `5` — Línea 5 Torrecuevas invierno (https://urbanosalmunecar.es/lineas-urbanas-almunecar/torrecuevas-linea-5-invierno/), retrieved 2026-08-10, confidence high. Page title reads 'Línea 5 Torrecuevas invierno' and the URL slug contains 'linea-5'. Same sitemap lastmod as the summer page (2026-05-14), so neither can be dismissed as simply older.
- `5` — OpenStreetMap bus route relations for Grupo Fajardo, via Overpass (https://overpass-api.de/api/interpreter), retrieved 2026-08-10, confidence medium. OSM relation ref='Línea 5', operator='Grupo Fajardo'.
