# Shape geometry evidence

One GeoJSON `LineString` per shape, referenced from `observations.csv` as

    shape:<SHAPE_ID>,geometry,geometry/<SHAPE_ID>.geojson,<source_id>,...

Polylines are too long to live in a readable CSV, but they still need
provenance, so the observation row carries the source, confidence and retrieval
date while the file carries the coordinates.

Geometry must come from real road alignment — operator/iBusGPS data, an observed
vehicle trace, or OSM roads. A straight line between two stops is not acceptable
in the production feed.
