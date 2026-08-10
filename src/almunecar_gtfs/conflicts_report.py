"""Generate ``docs/conflicts.md`` from the conflict register.

Disagreement is useful information. This report exists so that a reader can see,
per entity and field, exactly what each source claimed and what was decided —
including the claims that lost.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path

from almunecar_gtfs.provenance import Conflict, EvidenceStore, SourceType

COLUMN_ORDER: tuple[SourceType, ...] = (
    SourceType.OFFICIAL,
    SourceType.MUNICIPAL,
    SourceType.IBUSGPS,
    SourceType.MOOVIT,
    SourceType.OSM,
    SourceType.FIELD,
    SourceType.DERIVED,
)


def _cell(text: str | None) -> str:
    if not text:
        return "—"
    return text.replace("|", "\\|").replace("\n", " ")


def _resolution_cell(conflict: Conflict) -> str:
    if conflict.status == "resolved":
        return _cell(f"**{conflict.resolved_value}** — {conflict.resolution}")
    if conflict.status == "accepted_ambiguity":
        return _cell(f"accepted ambiguity — {conflict.resolution}")
    marker = " ⛔ blocks publication" if conflict.blocks_publication else ""
    detail = f" — {conflict.resolution}" if conflict.resolution else ""
    return _cell(f"unresolved{marker}{detail}")


def render_conflicts_markdown(evidence: EvidenceStore, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    conflicts = sorted(evidence.conflicts, key=lambda c: (c.status != "unresolved", c.key))
    unresolved = [c for c in conflicts if c.status == "unresolved"]
    blocking = [c for c in unresolved if c.blocks_publication]

    lines = [
        "# Source conflicts",
        "",
        f"*Generated {today.isoformat()} by `almunecar-gtfs conflicts`. Do not edit by hand —",
        "record decisions in `data/evidence/conflicts.yaml` and regenerate.*",
        "",
        f"{len(conflicts)} recorded conflict(s): {len(unresolved)} unresolved, "
        f"{len(blocking)} blocking publication.",
        "",
        "Conflicting source data is never discarded. A resolved row still shows every",
        "claim that was rejected, so a future reviewer can re-examine the decision",
        "instead of re-doing the research.",
        "",
    ]

    if not conflicts:
        lines += [
            "No conflicts recorded yet. That is expected before source acquisition has run,",
            "and suspicious afterwards: independent sources describing a real bus network",
            "almost always disagree about something.",
            "",
        ]
        return "\n".join(lines)

    header = ["Entity", "Field", *(t.value for t in COLUMN_ORDER), "Resolution"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")

    for conflict in conflicts:
        by_type: dict[SourceType, list[str]] = defaultdict(list)
        for claim in conflict.claims:
            source = evidence.sources.get(claim.source_id)
            source_type = source.source_type if source else SourceType.DERIVED
            by_type[source_type].append(f"`{claim.value}` ({claim.source_id})")
        row = [
            f"`{conflict.entity}`",
            conflict.field,
            *(_cell("<br>".join(by_type.get(t, []))) for t in COLUMN_ORDER),
            _resolution_cell(conflict),
        ]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    if unresolved:
        lines += ["## Unresolved detail", ""]
        for conflict in unresolved:
            lines.append(f"### `{conflict.entity}` — {conflict.field}")
            lines.append("")
            if conflict.blocks_publication:
                lines.append(
                    "**Blocks publication.** The affected entity is excluded from the feed "
                    "until this is settled."
                )
                lines.append("")
            for claim in conflict.claims:
                source = evidence.sources.get(claim.source_id)
                descriptor = f"{source.title} ({source.source_url})" if source else "unknown source"
                stale = " *(marked stale)*" if source and source.is_stale else ""
                lines.append(
                    f"- `{claim.value}` — {descriptor}, retrieved {claim.retrieved_at}, "
                    f"confidence {claim.confidence}{stale}"
                    + (f". {claim.notes}" if claim.notes else "")
                )
            lines.append("")
    return "\n".join(lines)


def write_conflicts_markdown(path: Path, evidence: EvidenceStore) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_conflicts_markdown(evidence), encoding="utf-8")
    return len([c for c in evidence.conflicts if c.status == "unresolved"])
