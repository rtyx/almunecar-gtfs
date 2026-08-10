"""iBusGPS - the operator's passenger information system.

Potentially the richest source: explicit stop coordinates, route geometry and,
later, live vehicle positions for GTFS-Realtime (plan task 15).

Inspection is conservative by design. Responses are cached, requests are
rate-limited by :mod:`almunecar_gtfs.sources.base`, and nothing here polls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

#: Endpoints confirmed by inspecting the page source, bundles and XHR traffic.
#: Empty until that inspection has actually been done.
ENDPOINTS: tuple[str, ...] = ()

_COORD_LITERAL = re.compile(
    r"[\[{]\s*(?:\"?lat\"?\s*:\s*)?(3[0-9]\.\d{3,})\s*,\s*(?:\"?lng?\"?\s*:\s*)?(-[0-9]\.\d{3,})"
)


@dataclass(frozen=True)
class EmbeddedGeometry:
    """A coordinate list found embedded in a page or bundle."""

    variable: str | None
    points: list[tuple[float, float]]


def find_embedded_coordinates(text: str) -> list[tuple[float, float]]:
    """Pull ``lat, lon`` pairs out of map-initialisation JavaScript.

    Returns raw candidates only. Whether a candidate is a stop, a shape vertex
    or a map centre is a judgement for reconciliation, not for the scraper.
    """
    found = []
    for match in _COORD_LITERAL.finditer(text):
        latitude, longitude = float(match.group(1)), float(match.group(2))
        found.append((latitude, longitude))
    return found


def load_cached_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
