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

OpenStreetMap requires registered redirect URIs to be https, so the loopback
listener speaks TLS using a self-signed certificate generated fresh each run.
Your browser will warn that it is untrusted; that is expected, and the only
thing crossing it is the authorisation code travelling to your own machine.
Override the default with ``OSM_REDIRECT_URI`` if your app registered another.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

API = os.environ.get("OSM_API", "https://api.openstreetmap.org")
AUTHORIZE = f"{API}/oauth2/authorize"
TOKEN = f"{API}/oauth2/token"
#: Must match a redirect URI registered on the OAuth application exactly — OSM
#: compares the string, not the host. Override when your app registered a
#: different one than the default.
REDIRECT_URI = os.environ.get("OSM_REDIRECT_URI", "https://localhost:3000")
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


def _wrap_tls(sock):
    """Wrap the loopback listener in a throwaway self-signed certificate.

    Generated fresh each run into a temporary directory and never written to the
    repository. It exists only because OSM insists a registered redirect URI be
    https; nothing sensitive is protected by it beyond the authorisation code
    hopping from your browser to a socket on the same machine.
    """
    directory = Path(tempfile.mkdtemp(prefix="almunecar-gtfs-tls-"))
    key, cert = directory / "key.pem", directory / "cert.pem"
    openssl = shutil.which("openssl")
    if openssl is None:
        raise SystemExit(
            "openssl is not on PATH, so the https loopback listener cannot be "
            "created. Use JOSM instead — see osm/README.md."
        )
    subprocess.run(
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "1",
         "-subj", "/CN=localhost",
         "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
        check=True,
        capture_output=True,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile=cert, keyfile=key)
    return context.wrap_socket(sock, server_side=True)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        query = urllib.parse.urlparse(self.path).query
        code = urllib.parse.parse_qs(query).get("code", [None])[0]
        if code:
            _CallbackHandler.code = code
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            b"<h1>Authorised</h1><p>You can close this tab and return to the terminal.</p>"
            if code
            else b"<p>Waiting for the authorisation redirect.</p>"
        )
        self.wfile.write(body)

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

    parsed = urllib.parse.urlparse(REDIRECT_URI)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    server = http.server.ThreadingHTTPServer((host, port), _CallbackHandler)
    if parsed.scheme == "https":
        # OpenStreetMap requires registered redirect URIs to be https, so the
        # loopback listener has to speak TLS. The certificate is generated here,
        # used once and thrown away; your browser will warn that it is not
        # trusted, which is correct and expected. The only thing crossing it is
        # the authorisation code travelling from your browser to your own
        # machine.
        server.socket = _wrap_tls(server.socket)
    server.timeout = 1

    print("Opening your browser to authorise. Log in to OpenStreetMap and approve.")
    if parsed.scheme == "https":
        print(
            f"Your browser will warn about a self-signed certificate for {host}. "
            "That is this script's own throwaway certificate — choose 'Advanced' "
            "and proceed. Safari sometimes refuses outright; Firefox and Chrome "
            "both offer the override."
        )
    print(f"If it does not open, visit:\n  {url}\n")
    webbrowser.open(url)

    # Serve until the redirect actually arrives. A single handle_request() is not
    # enough: browsers probe the port, request /favicon.ico, and abandon TLS
    # handshakes, any of which would otherwise consume the one request we get and
    # leave nothing listening when the real redirect lands.
    deadline = time.monotonic() + 300
    while _CallbackHandler.code is None and time.monotonic() < deadline:
        try:
            server.handle_request()
        except (ssl.SSLError, OSError) as error:
            print(f"  (ignoring a failed connection attempt: {error})")
    server.server_close()

    if not _CallbackHandler.code:
        raise SystemExit(
            "No authorisation code received within five minutes.\n"
            "If your browser refused the self-signed certificate outright, use "
            "JOSM instead — see osm/README.md, which needs no local listener."
        )

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
    if response.status_code != 200:
        # OpenStreetMap explains itself here; an opaque HTTPStatusError would
        # throw that explanation away, which is exactly when it is most needed.
        try:
            error = response.json()
        except ValueError:
            error = {"raw": response.text[:400]}
        hint = ""
        if error.get("error") == "invalid_client" and not client_secret:
            hint = (
                "\n\nThe application is registered as *confidential*, so OSM wants a "
                "client secret even though PKCE is in use. Either:\n"
                "  - set OSM_CLIENT_SECRET, or\n"
                "  - better, edit the app at "
                "https://www.openstreetmap.org/oauth2/applications and untick "
                "'Confidential application'. With PKCE the secret buys nothing, and "
                "a secret you never store cannot leak."
            )
        raise SystemExit(
            f"token exchange failed ({response.status_code}): "
            f"{json.dumps(error, ensure_ascii=False)}{hint}"
        )
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
