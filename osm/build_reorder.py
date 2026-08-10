#!/usr/bin/env python3
"""Regenerate the Torrecuevas relation reorder from the live OSM relation.

Reads relation 18501914 from the OSM API (no authentication needed), reorders
its platform members into the travel order given by the operator's own route
diagram, and writes a JOSM-openable ``.osm`` file.

Built from the *live* relation rather than a cached extract so the version
number is current — uploading a stale version is rejected by the API, which is
the right behaviour but a poor way to find out.

    python osm/build_reorder.py

Refuses to write anything if the live relation no longer contains exactly the
platforms this reorder was worked out against: if someone has edited it since,
the mapping needs re-checking by a human rather than re-applying blindly.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

RELATION_ID = 18501914
API = f"https://api.openstreetmap.org/api/0.6/relation/{RELATION_ID}"
OUTPUT = Path(__file__).parent / f"relation-{RELATION_ID}-reorder.osm"
USER_AGENT = "almunecar-gtfs/0.1 (+https://github.com/rtyx/almunecar-gtfs)"

STOP_NODE = 906081771

#: Platform members in travel order, read off the operator's route diagram
#: (data/evidence/images/torrecuevas-route-diagram.png) and verified against the
#: road geometry by ``almunecar_gtfs.qa.check_stop_order``.
PLATFORM_ORDER: tuple[int, ...] = (
    4266754568,   # Plaza de la Carrera
    4742153104,   # Barrio de San Sebastián I
    4742153105,   # Barrio de San Sebastián II
    4742153106,   # Laderas de Castelar
    12473808199,  # Peñuelas
    12473808200,  # Venta Luciano
    12473838001,  # Torrecuevas
    12473838002,  # Arcos de Torrecuevas
    12473838003,  # Cortijo Cahicillos  <- the apex; currently listed near the town
    9897655750,   # Arcos de Torrecuevas (return)
    12473838004,  # Torrecuevas (return)
    12473838005,  # Venta Luciano (return)
    12473838006,  # Peñuelas (return)
    12473838007,  # Laderas de Castelar (return)
    12473838008,  # Barrio de San Sebastián II (return)
    12473808198,  # Barrio de San Sebastián I (return)
    4266754568,   # Plaza de la Carrera (return)
)


def fetch_relation() -> ET.Element:
    response = httpx.get(API, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return ET.fromstring(response.text).find("relation")


def main() -> int:
    relation = fetch_relation()
    version = relation.get("version")
    members = relation.findall("member")
    live_platforms = {
        int(m.get("ref"))
        for m in members
        if m.get("type") == "node" and m.get("role") == "platform"
    }

    expected = set(PLATFORM_ORDER)
    if live_platforms != expected:
        print(
            "The live relation's platforms differ from the ones this reorder was "
            "worked out against.\n"
            f"  only upstream: {sorted(live_platforms - expected)}\n"
            f"  only here:     {sorted(expected - live_platforms)}\n"
            "Someone has edited it. Re-check the mapping against the operator's "
            "diagram before regenerating.",
            file=sys.stderr,
        )
        return 1

    ways = [m for m in members if m.get("type") == "way"]

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<osm version="0.6" generator="almunecar-gtfs">',
           f'  <relation id="{RELATION_ID}" version="{version}" action="modify">',
           f'    <member type="node" ref="{STOP_NODE}" role="stop"/>']
    for ref in PLATFORM_ORDER:
        out.append(f'    <member type="node" ref="{ref}" role="platform"/>')
    out.append(f'    <member type="node" ref="{STOP_NODE}" role="stop"/>')
    for way in ways:
        out.append(
            f'    <member type="way" ref="{way.get("ref")}" role="{way.get("role", "")}"/>'
        )
    for tag in relation.findall("tag"):
        key = tag.get("k").replace("&", "&amp;").replace('"', "&quot;")
        value = tag.get("v").replace("&", "&amp;").replace('"', "&quot;")
        out.append(f'    <tag k="{key}" v="{value}"/>')
    out += ["  </relation>", "</osm>"]

    OUTPUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} (relation version {version}, "
          f"{len(PLATFORM_ORDER)} platforms, {len(ways)} ways)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
