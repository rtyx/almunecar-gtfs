"""Autocares Urbanos Almunecar / Roalfa - the operator's own material.

Top of the hierarchy for route names, service periods and published departures.

The page inventory below is filled in by research and is deliberately explicit:
a URL that has not been confirmed to exist does not belong here, because a
guessed URL that 404s looks identical to a route that was withdrawn.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from almunecar_gtfs.sources.base import FetchResult, fetch


@dataclass(frozen=True)
class OperatorPage:
    source_id: str
    url: str
    title: str
    covers: str
    """What the page is evidence about, e.g. 'line 2 summer timetable'."""


#: Confirmed operator pages. Populated during research (plan task 3); every
#: entry must have been fetched successfully at least once.
PAGES: tuple[OperatorPage, ...] = ()


def fetch_pages(cache_dir: Path, *, force: bool = False) -> dict[str, FetchResult]:
    return {page.source_id: fetch(page.url, cache_dir, force=force) for page in PAGES}
