"""Source acquisition.

Every module here does exactly one thing: turn a source into
:class:`~almunecar_gtfs.provenance.Observation` rows. None of them may write
canonical data or GTFS files.
"""

from almunecar_gtfs.sources import base, ibusgps, moovit, municipal, official, osm

__all__ = ["base", "ibusgps", "moovit", "municipal", "official", "osm"]
