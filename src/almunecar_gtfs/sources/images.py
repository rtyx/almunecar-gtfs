"""The operator's published timetable and route-diagram images.

Every departure time in :mod:`~almunecar_gtfs.sources.official` was read off one
of these by hand. Keeping the images alongside the transcription is what makes
the transcription checkable: a reviewer can open the picture and the number side
by side instead of taking our word for it, and the archive survives the operator
reorganising their site.

The images are the operator's own material, reproduced unmodified with
attribution and source URLs. See ``data/evidence/images/README.md``.

Nothing here parses the images. They are evidence for a human; the machine-usable
facts live in ``observations.csv``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

MANIFEST_FILE = "images.yaml"
IMAGES_DIR = "images"


@dataclass(frozen=True)
class TimetableImage:
    file: str
    sha256: str
    bytes: int
    source_id: str
    source_url: str
    kind: str
    """``timetable`` | ``diagram`` | ``map`` | ``notice``."""

    depicts: str

    def path(self, evidence_dir: Path) -> Path:
        return evidence_dir / IMAGES_DIR / self.file


def load_manifest(evidence_dir: Path) -> list[TimetableImage]:
    path = evidence_dir / MANIFEST_FILE
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    return [TimetableImage(**item) for item in raw]


def by_source_url(evidence_dir: Path) -> dict[str, TimetableImage]:
    """Lets a transcription's cited image URL resolve to the committed copy."""
    return {image.source_url: image for image in load_manifest(evidence_dir)}


def verify(evidence_dir: Path) -> list[str]:
    """Check every manifest entry against the file on disk.

    A silently-replaced image would quietly invalidate the transcription that
    cites it, so the hash is part of the evidence, not a nicety.
    """
    problems: list[str] = []
    for image in load_manifest(evidence_dir):
        path = image.path(evidence_dir)
        if not path.exists():
            problems.append(f"{image.file}: listed in the manifest but missing from disk")
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != image.sha256:
            problems.append(
                f"{image.file}: sha256 is {digest[:12]}…, manifest says {image.sha256[:12]}…"
            )
        elif len(data) != image.bytes:
            problems.append(f"{image.file}: {len(data)} bytes, manifest says {image.bytes}")

    listed = {image.file for image in load_manifest(evidence_dir)}
    directory = evidence_dir / IMAGES_DIR
    if directory.exists():
        for path in sorted(directory.glob("*.png")):
            if path.name not in listed:
                problems.append(f"{path.name}: on disk but not in the manifest")
    return problems
