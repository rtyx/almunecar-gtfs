# Prepared OpenStreetMap fixes

Changes this project found while building the dataset, prepared so a mapper can
review and upload them. **Nothing here has been uploaded.** Applying them is a
deliberate act by a human with an OSM account, which is how it should be.

## `relation-18501914-reorder.osm` — Línea 5 Torrecuevas, member order

Relation [18501914](https://www.openstreetmap.org/relation/18501914) lists the
right platforms in the wrong order. It places `Cortijo Cahicillos`, the far apex
of the line, between two stops beside the town, so any consumer that walks the
relation in order gets a route that leaps 3.5 km out and back mid-journey.

The corrected order comes from the operator's own route diagram
(`data/evidence/images/torrecuevas-route-diagram.png`) and is verified against
the road geometry: with it, every platform matches the shape monotonically; with
the current order, `Cortijo Cahicillos` lands 3,471 m and `Torrecuevas` 2,432 m
from where the sequence puts them, while both sit within 10 m of the route.

Only the member *order* changes. No tags, geometry, nodes or ways are touched,
and the way members are left exactly as they were.

### How to apply

1. Open JOSM.
2. `File → Open…` and select `relation-18501914-reorder.osm`.
3. The relation is flagged `action="modify"`; review it in the relation editor.
4. Upload with a changeset comment such as:

   > Línea 5 Torrecuevas: reorder platform members into travel order, per the
   > operator's published route diagram (urbanosalmunecar.es)

JOSM will ask for your OSM login. Check the diff before uploading — the file is
generated, and a generated file deserves a human's eyes.

## Not included: the missing stops

The operator's diagram names eight calls that OSM has no node for at all:
`CEMENTERIO`, `EUCALIPTO`, `CAHICILLOS 2`, `VTA LUCIANO 2` and their return
counterparts.

They are deliberately **not** in this file. Adding a bus stop requires knowing
where the pole actually is, and no source consulted gives a position for any of
them. Guessing coordinates and uploading them would put invented data into a
public database — the precise failure mode this whole project exists to avoid.

They need a survey: walk or drive the line, record each pole, then add them.
