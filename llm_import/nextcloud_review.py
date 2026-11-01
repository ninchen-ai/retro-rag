"""Sichere Vorbereitung von Nextcloud-Review-Uploads."""

import base64
from urllib.parse import quote, urlsplit
from urllib.request import Request
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, build_opener, HTTPRedirectHandler

REVIEW_ROOT = "Retro-Computing/Import/review/"


def build_review_put_request(
    *,
    base_url: str,
    user: str,
    password: str,
    path: str,
    content: str,
) -> Request:
    """Erstellt eine WebDAV-PUT-Anfrage ohne Netzwerkzugriff."""

    parsed = urlsplit(base_url)

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Ungültige Nextcloud-Basis-URL")

    if (
        parsed.scheme == "http"
        and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
    ):
        raise ValueError(
            "Unverschlüsseltes HTTP nur über localhost erlaubt"
        )

    if not isinstance(user, str) or not user or "/" in user:
        raise ValueError("Ungültiger Nextcloud-Benutzer")

    if not isinstance(password, str) or not password:
        raise ValueError("Nextcloud-App-Passwort fehlt")

    if not isinstance(path, str):
        raise ValueError("Ungültiger Review-Pfad")

    if not path.startswith(REVIEW_ROOT):
        raise ValueError("Ziel liegt außerhalb des Review-Bereichs")

    relative = path[len(REVIEW_ROOT):]
    components = relative.split("/")

    if (
        not relative
        or any(
            component in {"", ".", ".."}
            or not component.isascii()
            or not all(
                char.isalnum() or char in "._-"
                for char in component
            )
            for component in components
        )
        or not path.endswith(".md")
    ):
        raise ValueError("Unsicherer Review-Dateipfad")

    if not isinstance(content, str) or not content.strip():
        raise ValueError("Leerer Markdown-Inhalt")

    encoded_path = quote(path, safe="/")

    url = (
        base_url.rstrip("/")
        + "/remote.php/dav/files/"
        + quote(user, safe="")
        + "/"
        + encoded_path
    )

    credentials = base64.b64encode(
        f"{user}:{password}".encode("utf-8")
    ).decode("ascii")

    return Request(
        url=url,
        data=content.encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "text/markdown; charset=utf-8",
            "If-None-Match": "*",
        },
    )

class NoRedirectHandler(HTTPRedirectHandler):
    """Verhindert automatische HTTP-Weiterleitungen."""

    def redirect_request(
        self, req, fp, code, msg, headers, newurl
    ):
        return None

def execute_review_put(request: Request) -> dict:
    """Führt eine vorbereitete PUT-Anfrage aus.

    Nur für den späteren expliziten Upload vorgesehen.
    """

    if request.get_method() != "PUT":
        raise ValueError("Nur PUT-Anfragen erlaubt")

    if request.get_header("If-none-match") != "*":
        raise ValueError("Überschreibschutz fehlt")

    try:
        with build_opener(NoRedirectHandler()).open(
            request, timeout=30
        ) as response:
            if response.status != 201:
                raise RuntimeError(
                    f"Unerwartete WebDAV-Antwort: HTTP {response.status}"
                )

            return {
                "status": "CREATED",
                "http_status": response.status,
            }

    except HTTPError as exc:
        if exc.code in {409, 412}:
            return {
                "status": "CONFLICT",
                "http_status": exc.code,
            }

        raise RuntimeError(
            f"WebDAV-Upload fehlgeschlagen: HTTP {exc.code}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            "WebDAV-Verbindung fehlgeschlagen"
        ) from exc