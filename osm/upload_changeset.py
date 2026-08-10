#!/usr/bin/env python3
"""Upload a prepared OSM change under your own account.

You run this; it opens your browser, you log in to OpenStreetMap and approve.
The resulting token is written to your user cache directory, never to this
repository and never into a chat. No password is handled by this script — the
login happens on openstreetmap.org, in your browser, as it should.

    export OSM_CLIENT_ID=...          # from My Settings -> OAuth 2 applications
    export OSM_CLIENT_SECRET=...      # optional; omit for a public client
    python osm/upload_changeset.py osm/relation-18501914-reorder.osm \\
        --comment "Línea 5 Torrecuevas: reorder platform members into travel order"

Add ``--dry-run`` to print the osmChange payload and exit without touching the
API or authenticating. Do that first.

The registered redirect URI must be ``http://localhost:3000``. OpenStreetMap
permits plain http for localhost; an https redirect would need a local
certificate for no benefit.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

API = os.environ.get("OSM_API", "https://api.openstreetmap.org")
AUTHORIZE = f"{API}/oauth2/authorize"
TOKEN = f"{API}/oauth2/token"
REDIRECT_URI = "http://localhost:3000"
SCOPES = "write_api read_prefs"

TOKEN_CACHE = (
    Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    / "almunecar-gtfs"
    / "osm-token.json"
)

USER_AGENT = "almunecar-gtfs/0.1 (+https://github.com/rtyx/almunecar-gtfs)"


# -- osmChange -----------------------------------------------------------


def to_osmchange(osm_file: Path, changeset_id: str | int) -> str:
    """Turn a JOSM-style .osm file into an osmChange upload payload.

    Only elements the file marks ``action="modify"`` are uploaded; everything
    else in the file is context that JOSM needs and the API does not.
    """
    root = ET.parse(osm_file).getroot()
    modified = [e for e in root if e.get("action") == "modify"]
    if not modified:
        raise SystemExit(f"{osm_file}: nothing marked action=\"modify\"")

    out = ['<osmChange version="0.6" generator="almunecar-gtfs">', "  <modify>"]
    for element in modified:
        copy = ET.fromstring(ET.tostring(element))
        copy.attrib.pop("action", None)
        copy.set("changeset", str(changeset_id))
        out.append("    " + ET.tostring(copy, encoding="unicode").strip())
    out += ["  </modify>", "</osmChange>"]
    return "\n".join(out)


def summarise(osm_file: Path) -> str:
    root = ET.parse(osm_file).getroot()
    lines = []
    for element in root:
        if element.get("action") != "modify":
            continue
        members = element.findall("member")
        lines.append(
            f"  modify {element.tag} {element.get('id')} "
            f"({len(members)} members)" if members else
            f"  modify {element.tag} {element.get('id')}"
        )
    return "\n".join(lines)


# -- OAuth ---------------------------------------------------------------


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        query = urllib.parse.urlparse(self.path).query
        _CallbackHandler.code = urllib.parse.parse_qs(query).get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<h1>Authorised</h1><p>You can close this tab and return to the terminal.</p>"
        )

    def log_message(self, *args) -> None:  # noqa: D102 - silence the default logging
        return


def authorise(client_id: str, client_secret: str | None) -> str:
    """Run the authorisation-code flow with PKCE and return an access token."""
    if TOKEN_CACHE.exists():
        cached = json.loads(TOKEN_CACHE.read_text())
        if token := cached.get("access_token"):
            return token

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(16)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{AUTHORIZE}?{urllib.parse.urlencode(params)}"

    server = http.server.HTTPServer(("localhost", 3000), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("Opening your browser to authorise. Log in to OpenStreetMap and approve.")
    print(f"If it does not open, visit:\n  {url}\n")
    webbrowser.open(url)
    thread.join(timeout=300)
    server.server_close()

    if not _CallbackHandler.code:
        raise SystemExit("no authorisation code received within five minutes")

    payload = {
        "grant_type": "authorization_code",
        "code": _CallbackHandler.code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    if client_secret:
        payload["client_secret"] = client_secret

    response = httpx.post(TOKEN, data=payload, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    token = response.json()["access_token"]

    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps({"access_token": token}), encoding="utf-8")
    TOKEN_CACHE.chmod(0o600)
    print(f"Token cached at {TOKEN_CACHE} (delete it to re-authorise).")
    return token


# -- upload --------------------------------------------------------------


def upload(osm_file: Path, comment: str, token: str) -> int:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    client = httpx.Client(headers=headers, timeout=60)

    changeset_xml = f"""<osm><changeset>
  <tag k="created_by" v="almunecar-gtfs"/>
  <tag k="comment" v="{comment}"/>
  <tag k="source" v="operator route diagram, urbanosalmunecar.es"/>
</changeset></osm>"""
    created = client.put(
        f"{API}/api/0.6/changeset/create",
        content=changeset_xml.encode(),
        headers={"Content-Type": "text/xml"},
    )
    created.raise_for_status()
    changeset_id = created.text.strip()
    print(f"opened changeset {changeset_id}")

    try:
        result = client.post(
            f"{API}/api/0.6/changeset/{changeset_id}/upload",
            content=to_osmchange(osm_file, changeset_id).encode(),
            headers={"Content-Type": "text/xml"},
        )
        result.raise_for_status()
        print(result.text.strip()[:500])
    finally:
        client.put(f"{API}/api/0.6/changeset/{changeset_id}/close")
        print(f"closed changeset {changeset_id}")
        client.close()

    print(f"\nhttps://www.openstreetmap.org/changeset/{changeset_id}")
    return int(changeset_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--comment", required=True, help="changeset comment")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be uploaded and exit; no network, no login",
    )
    args = parser.parse_args(argv)

    if not args.file.exists():
        raise SystemExit(f"{args.file} does not exist")

    print(f"{args.file}:")
    print(summarise(args.file))
    print()

    if args.dry_run:
        print(to_osmchange(args.file, "PLACEHOLDER"))
        return 0

    client_id = os.environ.get("OSM_CLIENT_ID")
    if not client_id:
        raise SystemExit(
            "OSM_CLIENT_ID is not set.\n"
            "Create an app at https://www.openstreetmap.org/oauth2/applications "
            "with redirect URI http://localhost:3000 and the write_api permission."
        )

    token = authorise(client_id, os.environ.get("OSM_CLIENT_SECRET"))
    upload(args.file, args.comment, token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
