"""Moovit - secondary reference, used for discrepancy detection only.

Moovit never wins a reconciliation against current operator or municipal data.
Its job here is to make us notice when our stop count, stop order or first and
last departures disagree with an independently-built dataset.

Nothing in this module copies Moovit's data into the canonical dataset. It
produces comparison rows for :mod:`almunecar_gtfs.compare`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MoovitRoute:
    """A route as Moovit presents it, transcribed by hand or by extraction."""

    route_label: str
    direction: str
    stop_names: list[str] = field(default_factory=list)
    first_departure: str | None = None
    last_departure: str | None = None
    trip_duration_minutes: int | None = None
    source_url: str | None = None
    retrieved_at: str | None = None


#: Transcribed Moovit observations. Kept as data rather than scraped on demand:
#: Moovit blocks automated access, and brittle scraping is worse than an honest
#: manual transcription with a date on it.
ROUTES: tuple[MoovitRoute, ...] = ()
