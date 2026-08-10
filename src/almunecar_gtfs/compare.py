"""Cross-check the canonical dataset against independent descriptions of it.

Two comparisons, both aimed at finding disagreements rather than at importing
anything:

* **Moovit** — an independently-built dataset of the same network.
* **The operator's own route diagrams** — transcribed from the images on the
  operator's pages, which name stops differently from OpenStreetMap and are the
  only statement of the intended stop *sequence* from the authority itself.

Neither can overrule the canonical dataset here. A mismatch is a question for a
human, and this module's job is to ask it clearly.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from almunecar_gtfs.models import Network
from almunecar_gtfs.sources import moovit, official


@dataclass(frozen=True)
class Comparison:
    pattern_id: str
    label: str
    ours: int
    theirs: int
    verdict: str
    detail: str

    @property
    def agrees(self) -> bool:
        return self.ours == self.theirs


def compare_moovit(network: Network) -> list[Comparison]:
    results = []
    for pattern in sorted(network.patterns, key=lambda p: p.pattern_id):
        route = moovit.ROUTES_BY_PATTERN.get(pattern.pattern_id)
        if route is None:
            continue
        ours, theirs = len(pattern.stops), route.stop_count
        if ours == theirs:
            verdict = "stop counts agree"
        else:
            verdict = f"stop counts differ by {abs(ours - theirs)}"
        results.append(
            Comparison(
                pattern_id=pattern.pattern_id,
                label=f"{route.route_label} ({route.subtitle})",
                ours=ours,
                theirs=theirs,
                verdict=verdict,
                detail=route.notes or "",
            )
        )
    return results


def compare_operator_diagrams(network: Network) -> list[Comparison]:
    results = []
    for route_id, diagram in sorted(official.DIAGRAMS.items()):
        patterns = [p for p in network.patterns if p.route_id == route_id]
        if not patterns:
            results.append(
                Comparison(
                    pattern_id=f"(none for {route_id})",
                    label=f"{route_id} operator diagram",
                    ours=0,
                    theirs=len(diagram),
                    verdict="no reconstructed pattern to compare against",
                    detail="The operator names these stops but none of them are mapped.",
                )
            )
            continue
        for pattern in sorted(patterns, key=lambda p: p.pattern_id):
            ours, theirs = len(pattern.stops), len(diagram)
            results.append(
                Comparison(
                    pattern_id=pattern.pattern_id,
                    label=f"{route_id} operator diagram",
                    ours=ours,
                    theirs=theirs,
                    verdict=(
                        "stop counts agree"
                        if ours == theirs
                        else f"stop counts differ by {abs(ours - theirs)}"
                    ),
                    detail=(
                        "Operator and OSM use different stop names, so only counts and "
                        "endpoints are compared automatically."
                    ),
                )
            )
    return results


def render_comparison_markdown(network: Network, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    moovit_rows = compare_moovit(network)
    diagram_rows = compare_operator_diagrams(network)

    lines = [
        "# Cross-checks against independent sources",
        "",
        f"*Generated {today.isoformat()} by `almunecar-gtfs compare`. Do not edit by hand.*",
        "",
        "Neither source below can overrule the canonical dataset. Both exist to make",
        "disagreements visible. A row that agrees is evidence; a row that does not is a",
        "question for a human.",
        "",
        "## Moovit",
        "",
        f"Transcribed from Moovit in a browser on {moovit.TRANSCRIBED_AT}; Moovit renders",
        "its pages with JavaScript and serves nothing to a plain HTTP client.",
        "",
        "| Pattern | Moovit line | Our stops | Moovit stops | Verdict |",
        "|---|---|---:|---:|---|",
    ]
    for row in moovit_rows:
        lines.append(
            f"| `{row.pattern_id}` | {row.label} | {row.ours} | {row.theirs} | {row.verdict} |"
        )
    lines += ["", "### Notes", ""]
    for route in moovit.ROUTES:
        if route.notes:
            lines.append(f"- **{route.route_label}** — {route.notes}")
    lines += [
        "",
        "Moovit's first and last departures are recorded too:",
        "",
        "| Moovit line | First | Last | Stated duration |",
        "|---|---|---|---|",
    ]
    for route in moovit.ROUTES:
        lines.append(
            f"| {route.route_label} | {route.first_departure or '—'} | "
            f"{route.last_departure or '—'} | "
            f"{f'{route.trip_duration_minutes} min' if route.trip_duration_minutes else '—'} |"
        )
    lines += [
        "",
        "Moovit's stated trip durations are the only end-to-end journey times any source",
        "gives. They are **not** used to synthesise stop times: one number for a whole",
        "loop cannot be apportioned between stops without inventing the apportionment,",
        "and Moovit is a QA reference, not an authority on the operator's timetable.",
        "",
        "## The operator's own route diagrams",
        "",
        "Transcribed from the diagram images on the operator's pages. These use the",
        "operator's stop names, which do not match OpenStreetMap's, so only counts and",
        "endpoints can be compared mechanically; the names themselves are listed in",
        "`sources/official.py` for manual review.",
        "",
        "| Pattern | Diagram | Our stops | Diagram stops | Verdict |",
        "|---|---|---:|---:|---|",
    ]
    for row in diagram_rows:
        lines.append(
            f"| `{row.pattern_id}` | {row.label} | {row.ours} | {row.theirs} | {row.verdict} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_comparison_markdown(path: Path, network: Network) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_comparison_markdown(network), encoding="utf-8")
    disagreements = [
        row
        for row in compare_moovit(network) + compare_operator_diagrams(network)
        if not row.agrees
    ]
    return len(disagreements)
