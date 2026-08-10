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

### Regenerating it

`build_reorder.py` rebuilds this file from the *live* relation, so the version
number is always current — uploading a stale version is rejected by the API,
which is correct behaviour but an unpleasant way to discover the problem. It
refuses to write anything if the relation's platforms have changed upstream,
because then the mapping needs a human to re-check it, not a blind re-apply.

```bash
python osm/build_reorder.py
```

### How to apply, option A: JOSM (simplest)

1. Open JOSM.
2. `File → Open…` and select `relation-18501914-reorder.osm`.
3. The relation is flagged `action="modify"`; review it in the relation editor.
4. Upload with a changeset comment such as:

   > Línea 5 Torrecuevas: reorder platform members into travel order, per the
   > operator's published route diagram (urbanosalmunecar.es)

JOSM will ask for your OSM login and handles the OAuth flow itself, so your
password goes only to openstreetmap.org. Check the diff before uploading — the
file is generated, and a generated file deserves a human's eyes.

### How to apply, option B: the upload script

For scripted uploads, `upload_changeset.py` runs the OAuth 2 authorisation-code
flow with PKCE: it opens your browser, you log in and approve on
openstreetmap.org, and the resulting token is cached in your user cache
directory (`~/.cache/almunecar-gtfs/osm-token.json`, mode 600). The token never
enters this repository.

Register an app at <https://www.openstreetmap.org/oauth2/applications> with
redirect URI `https://localhost:3000` and the `write_api` permission.

OpenStreetMap insists redirect URIs be https, so the loopback listener speaks
TLS using a self-signed certificate generated fresh on each run and thrown away
afterwards. Your browser will warn that it is untrusted — that is expected;
choose *Advanced* and proceed. The only thing crossing that connection is the
authorisation code travelling from your browser to a socket on your own machine.

Then:

```bash
python osm/upload_changeset.py osm/relation-18501914-reorder.osm --comment "..." --dry-run
```

```bash
export OSM_CLIENT_ID=...
python osm/upload_changeset.py osm/relation-18501914-reorder.osm \
  --comment "Línea 5 Torrecuevas: reorder platform members into travel order"
```

Run `--dry-run` first; it prints the exact osmChange payload and touches
neither the network nor your account.

## Not included: the missing stops

The operator's diagram names eight calls that OSM has no node for at all:
`CEMENTERIO`, `EUCALIPTO`, `CAHICILLOS 2`, `VTA LUCIANO 2` and their return
counterparts.

They are deliberately **not** in this file. Adding a bus stop requires knowing
where the pole actually is, and no source consulted gives a position for any of
them. Guessing coordinates and uploading them would put invented data into a
public database — the precise failure mode this whole project exists to avoid.

They need a survey: walk or drive the line, record each pole, then add them.
