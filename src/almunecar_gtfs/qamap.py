"""Interactive QA map for human verification before publication.

The point of this map is not to look at the network; it is to answer "why is
``ALM_0042`` there?" in one click. Each stop popup lists the coordinate that
won, every coordinate that lost, the source behind each, and any QA flag the
stop raised.

Leaflet is loaded from a CDN. This file is a local review artifact under
``qa/``; it is git-ignored and never published.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from almunecar_gtfs.models import Network
from almunecar_gtfs.provenance import EvidenceDomain, EvidenceStore
from almunecar_gtfs.qa import Finding, Severity

LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"

SEVERITY_COLOURS = {
    Severity.ERROR: "#d1344c",
    Severity.WARNING: "#e0872b",
    Severity.INFO: "#2b7de0",
}
CLEAN_COLOUR = "#2f9e5f"

PATTERN_COLOURS = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#17becf",
)


def _stop_payload(
    network: Network, evidence: EvidenceStore, findings_by_entity: dict[str, list[Finding]]
) -> list[dict]:
    payload = []
    for stop in network.stops:
        entity = f"stop:{stop.internal_stop_id}"
        candidates = []
        for observation in evidence.ranked(EvidenceDomain.STOP_COORD, entity, "coordinate"):
            source = evidence.source_of(observation)
            candidates.append(
                {
                    "source_id": observation.source_id,
                    "source_title": source.title,
                    "source_type": str(source.source_type),
                    "url": observation.source_url or source.source_url,
                    "value": observation.value,
                    "confidence": str(observation.confidence),
                    "evidence_kind": str(observation.evidence_kind or ""),
                    "retrieved_at": observation.retrieved_at.isoformat(),
                    "chosen": observation.source_id == stop.source_id,
                    "notes": observation.notes or "",
                }
            )
        flags = [
            {"severity": str(f.severity), "code": f.code, "message": f.message}
            for f in findings_by_entity.get(entity, [])
        ]
        worst = Severity.INFO
        for finding in findings_by_entity.get(entity, []):
            if finding.severity is Severity.ERROR:
                worst = Severity.ERROR
                break
            if finding.severity is Severity.WARNING:
                worst = Severity.WARNING
        payload.append(
            {
                "id": stop.internal_stop_id,
                "name": stop.name,
                "lat": stop.latitude,
                "lon": stop.longitude,
                "municipality": stop.municipality,
                "confidence": str(stop.confidence),
                "chosen_source": stop.source_id,
                "direction_hint": stop.direction_hint or "",
                "pair_stop_id": stop.pair_stop_id or "",
                "osm_node_id": stop.osm_node_id,
                "colour": SEVERITY_COLOURS[worst] if flags else CLEAN_COLOUR,
                "candidates": candidates,
                "flags": flags,
            }
        )
    return payload


def _shape_payload(network: Network) -> list[dict]:
    payload = []
    patterns_by_shape: dict[str, list] = defaultdict(list)
    for pattern in network.patterns:
        if pattern.shape_id:
            patterns_by_shape[pattern.shape_id].append(pattern)

    for index, shape in enumerate(sorted(network.shapes, key=lambda s: s.shape_id)):
        patterns = patterns_by_shape.get(shape.shape_id, [])
        payload.append(
            {
                "shape_id": shape.shape_id,
                "colour": PATTERN_COLOURS[index % len(PATTERN_COLOURS)],
                "points": [[lat, lon] for lat, lon in shape.points],
                "source_id": shape.source_id,
                "confidence": str(shape.confidence),
                "patterns": [
                    {
                        "pattern_id": p.pattern_id,
                        "route_id": p.route_id,
                        "direction": "outbound" if p.direction_id == 0 else "inbound",
                        "season": str(p.season),
                        "headsign": p.headsign,
                        "stops": len(p.stops),
                        "status": str(p.status),
                        "conditional": p.conditional or "",
                    }
                    for p in sorted(patterns, key=lambda p: p.pattern_id)
                ],
            }
        )
    return payload


def _conflict_payload(evidence: EvidenceStore) -> list[dict]:
    return [
        {
            "entity": conflict.entity,
            "field": conflict.field,
            "status": conflict.status,
            "claims": [
                {"source_id": c.source_id, "value": c.value, "confidence": str(c.confidence)}
                for c in conflict.claims
            ],
            "resolution": conflict.resolution or "",
        }
        for conflict in evidence.conflicts
    ]


def render_qa_map(
    network: Network, evidence: EvidenceStore, findings: Sequence[Finding] = ()
) -> str:
    findings_by_entity: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        findings_by_entity[finding.entity].append(finding)

    data = {
        "stops": _stop_payload(network, evidence, findings_by_entity),
        "shapes": _shape_payload(network),
        "conflicts": _conflict_payload(evidence),
        "agency": network.agency.agency_name,
        "feed_version": network.feed_info.feed_version,
        "official": network.agency.is_official_feed,
    }
    centre = (
        [
            sum(s.latitude for s in network.stops) / len(network.stops),
            sum(s.longitude for s in network.stops) / len(network.stops),
        ]
        if network.stops
        else [36.7340, -3.6910]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Almunecar GTFS - QA map</title>
<link rel="stylesheet" href="{LEAFLET_CSS}">
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 14px/1.45 system-ui, -apple-system, sans-serif; }}
  #map {{ position: absolute; inset: 0 380px 0 0; }}
  #side {{ position: absolute; inset: 0 0 0 auto; width: 380px; overflow-y: auto;
           padding: 16px; background: Canvas; border-left: 1px solid #8884; }}
  h1 {{ font-size: 16px; margin: 0 0 4px; }}
  h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
        opacity: .6; margin: 20px 0 8px; }}
  .muted {{ opacity: .65; font-size: 12px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
  td, th {{ text-align: left; padding: 3px 6px; border-bottom: 1px solid #8883;
            vertical-align: top; }}
  .chosen {{ font-weight: 600; }}
  .chosen td {{ background: #2f9e5f22; }}
  .flag {{ padding: 6px 8px; border-radius: 4px; margin-bottom: 6px; font-size: 12px; }}
  .error {{ background: #d1344c22; border-left: 3px solid #d1344c; }}
  .warning {{ background: #e0872b22; border-left: 3px solid #e0872b; }}
  .info {{ background: #2b7de022; border-left: 3px solid #2b7de0; }}
  .banner {{ background: #e0872b22; border: 1px solid #e0872b; padding: 8px;
             border-radius: 4px; font-size: 12px; margin-bottom: 12px; }}
  code {{ font-size: 12px; }}
</style>
</head>
<body>
<div id="map"></div>
<div id="side">
  <h1>Almunecar GTFS - QA map</h1>
  <div class="muted" id="header"></div>
  <div id="banner"></div>
  <div id="detail"><p class="muted">Click a stop or a route to see why it looks the way
  it does.</p></div>
</div>
<script src="{LEAFLET_JS}"></script>
<script>
const DATA = {json.dumps(data, ensure_ascii=False)};
const map = L.map('map').setView({json.dumps(centre)}, 13);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);

document.getElementById('header').textContent =
  `${{DATA.agency}} - feed version ${{DATA.feed_version}} - ` +
  `${{DATA.stops.length}} stops, ${{DATA.shapes.length}} shapes`;

if (!DATA.official) {{
  document.getElementById('banner').innerHTML =
    '<div class="banner">Unofficial dataset. The operator has not authorised ' +
    'publication, so nothing here may be presented as an official feed.</div>';
}}

const esc = (value) => String(value ?? '').replace(/[&<>"]/g,
  (c) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]));
const detail = document.getElementById('detail');

function showStop(stop) {{
  const rows = stop.candidates.map((candidate) => `
    <tr class="${{candidate.chosen ? 'chosen' : ''}}">
      <td>${{candidate.chosen ? '&#10003;' : ''}}</td>
      <td>${{esc(candidate.source_id)}}<br>
          <span class="muted">${{esc(candidate.source_type)}}${{
            candidate.evidence_kind ? ' / ' + esc(candidate.evidence_kind) : ''}}</span></td>
      <td><code>${{esc(candidate.value)}}</code><br>
          <span class="muted">${{esc(candidate.confidence)}},
          ${{esc(candidate.retrieved_at)}}</span></td>
    </tr>`).join('');
  const flags = stop.flags.map((flag) =>
    `<div class="flag ${{esc(flag.severity)}}"><strong>${{esc(flag.code)}}</strong><br>
     ${{esc(flag.message)}}</div>`).join('');
  detail.innerHTML = `
    <h2>${{esc(stop.id)}}</h2>
    <p><strong>${{esc(stop.name)}}</strong><br>
       <span class="muted">${{esc(stop.municipality)}}
       ${{stop.direction_hint ? ' - ' + esc(stop.direction_hint) : ''}}</span></p>
    <p class="muted">Chosen coordinate from <code>${{esc(stop.chosen_source)}}</code>,
       confidence ${{esc(stop.confidence)}}${{
       stop.pair_stop_id ? `, pairs with <code>${{esc(stop.pair_stop_id)}}</code>` : ''}}.</p>
    ${{flags ? '<h2>Flags</h2>' + flags : ''}}
    <h2>Coordinate evidence (best first)</h2>
    <table><tbody>${{rows || '<tr><td class="muted">none recorded</td></tr>'}}</tbody></table>`;
}}

function showShape(shape) {{
  const patterns = shape.patterns.map((pattern) => `
    <tr><td><code>${{esc(pattern.pattern_id)}}</code><br>
        <span class="muted">${{esc(pattern.direction)}}, ${{esc(pattern.season)}},
        ${{pattern.stops}} stops, ${{esc(pattern.status)}}</span>
        ${{pattern.conditional ? '<br><em>' + esc(pattern.conditional) + '</em>' : ''}}</td></tr>`
  ).join('');
  detail.innerHTML = `
    <h2>${{esc(shape.shape_id)}}</h2>
    <p class="muted">Geometry from <code>${{esc(shape.source_id)}}</code>,
       confidence ${{esc(shape.confidence)}}.</p>
    <h2>Patterns using it</h2>
    <table><tbody>${{patterns || '<tr><td class="muted">none</td></tr>'}}</tbody></table>`;
}}

DATA.shapes.forEach((shape) => {{
  L.polyline(shape.points, {{ color: shape.colour, weight: 4, opacity: 0.75 }})
    .on('click', () => showShape(shape))
    .addTo(map);
}});

DATA.stops.forEach((stop) => {{
  L.circleMarker([stop.lat, stop.lon], {{
    radius: 6, color: '#fff', weight: 1.5, fillColor: stop.colour, fillOpacity: 0.95
  }}).bindTooltip(`${{stop.id}} - ${{stop.name}}`)
    .on('click', () => showStop(stop))
    .addTo(map);
}});
</script>
</body>
</html>
"""


def write_qa_map(
    path: Path, network: Network, evidence: EvidenceStore, findings: Sequence[Finding] = ()
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_qa_map(network, evidence, findings), encoding="utf-8")
    return path
