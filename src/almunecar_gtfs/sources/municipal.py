"""Ayuntamiento de Almunecar documents.

Second in the hierarchy for schedules, and the best available source for
municipal boundaries and any GIS-quality stop positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from almunecar_gtfs.sources.base import FetchResult, fetch


@dataclass(frozen=True)
class MunicipalDocument:
    source_id: str
    url: str
    title: str
    published: str | None
    """Publication date as printed on the document, when it states one."""


DOCUMENTS: tuple[MunicipalDocument, ...] = ()


def fetch_documents(cache_dir: Path, *, force: bool = False) -> dict[str, FetchResult]:
    return {doc.source_id: fetch(doc.url, cache_dir, force=force) for doc in DOCUMENTS}
