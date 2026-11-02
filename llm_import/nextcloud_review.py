"""Sichere Vorbereitung von Nextcloud-Review-Uploads."""

import base64
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request
from urllib.error import HTTPError, URLError
from urllib.request import urlopen, build_opener, HTTPRedirectHandler
from xml.etree import ElementTree as ET

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

def _execute_review_put(request: Request) -> dict:
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
        if exc.code == 412:
            return {
                "status": "CONFLICT",
                "http_status": 412,
            }

        if exc.code == 409:
            return {
                "status": "CONFLICT",
                "http_status": 409,
            }

        raise RuntimeError(
            f"WebDAV-Upload fehlgeschlagen: HTTP {exc.code}"
        ) from exc

        raise RuntimeError(
            f"WebDAV-Upload fehlgeschlagen: HTTP {exc.code}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            "WebDAV-Verbindung fehlgeschlagen"
        ) from exc

def upload_review_file(
    *,
    base_url: str,
    user: str,
    password: str,
    path: str,
    content: str,
) -> dict:
    """Lädt ausschließlich eine validierte Review-Datei hoch."""

    request = build_review_put_request(
        base_url=base_url,
        user=user,
        password=password,
        path=path,
        content=content,
    )

    return _execute_review_put(request)

def build_review_mkcol_request(
    *,
    base_url: str,
    user: str,
    password: str,
    path: str,
) -> Request:
    """Erstellt eine sichere MKCOL-Anfrage ohne Netzwerkzugriff."""

    if not isinstance(path, str) or not path.endswith("/"):
        raise ValueError("MKCOL benötigt einen Verzeichnispfad")

    # Wir verwenden den bestehenden PUT-Builder zur Validierung
    # der Verbindungsparameter und des geschützten Zielbereichs.
    probe = build_review_put_request(
        base_url=base_url,
        user=user,
        password=password,
        path=path + "__validation__.md",
        content="# validation",
    )

    directory_url = probe.full_url.rsplit("/", 1)[0] + "/"

    return Request(
        url=directory_url,
        method="MKCOL",
        headers={
            "Authorization": probe.get_header("Authorization"),
        },
    )

def create_review_directory(
    *,
    base_url: str,
    user: str,
    password: str,
    path: str,
) -> dict:
    """Erstellt ein Review-Verzeichnis über WebDAV."""

    request = build_review_mkcol_request(
        base_url=base_url,
        user=user,
        password=password,
        path=path,
    )

    try:
        with build_opener(NoRedirectHandler()).open(
            request, timeout=30
        ) as response:

            if response.status != 201:
                raise RuntimeError(
                    f"Unerwartete MKCOL-Antwort: HTTP {response.status}"
                )

            return {
                "status": "CREATED",
                "http_status": 201,
                "path": path,
            }

    except HTTPError as exc:
        if exc.code == 405:
            confirmed = verify_review_directory(
                base_url=base_url,
                user=user,
                password=password,
                path=path,
            )

            if not confirmed:
                raise RuntimeError(
                    "MKCOL meldet HTTP 405, aber am Ziel "
                    "ist kein Verzeichnis nachweisbar"
                ) from exc

            return {
                "status": "EXISTS",
                "http_status": 405,
                "path": path,
            }

        raise RuntimeError(
            f"MKCOL fehlgeschlagen: HTTP {exc.code}"
        ) from exc

        raise RuntimeError(
            f"MKCOL fehlgeschlagen: HTTP {exc.code}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            "WebDAV-Verbindung bei MKCOL fehlgeschlagen"
        ) from exc

def verify_review_directory(
    *,
    base_url: str,
    user: str,
    password: str,
    path: str,
) -> bool:
    """Prüft per PROPFIND, ob ein Review-Verzeichnis existiert."""

    probe = build_review_mkcol_request(
        base_url=base_url,
        user=user,
        password=password,
        path=path,
    )

    body = (
        b'<?xml version="1.0" encoding="utf-8"?>'
        b'<d:propfind xmlns:d="DAV:">'
        b'<d:prop><d:resourcetype/></d:prop>'
        b'</d:propfind>'
    )

    request = Request(
        url=probe.full_url,
        data=body,
        method="PROPFIND",
        headers={
            "Authorization": probe.get_header("Authorization"),
            "Depth": "0",
            "Content-Type": "application/xml",
        },
    )

    try:
        with build_opener(NoRedirectHandler()).open(
            request, timeout=30
        ) as response:
            if response.status != 207:
                raise RuntimeError(
                    f"Unerwartete PROPFIND-Antwort: HTTP {response.status}"
                )

            xml = ET.fromstring(response.read())

    except HTTPError as exc:
        if exc.code == 404:
            return False

        raise RuntimeError(
            f"PROPFIND fehlgeschlagen: HTTP {exc.code}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(
            "WebDAV-Verbindung bei PROPFIND fehlgeschlagen"
        ) from exc

    ns = {"d": "DAV:"}

    if xml.tag != "{DAV:}multistatus":
        raise RuntimeError("Ungültige PROPFIND-Antwort")

    responses = xml.findall("d:response", ns)

    if len(responses) != 1:
        raise RuntimeError(
            "Unerwartete Anzahl PROPFIND-Ergebnisse"
        )

    item = responses[0]

    href = item.findtext("d:href", namespaces=ns)

    if not href:
        raise RuntimeError("PROPFIND-Antwort ohne href")

    expected = urlsplit(probe.full_url)

    returned = urlsplit(href)

    if returned.scheme or returned.netloc:
        if (
            returned.scheme != expected.scheme
            or returned.netloc != expected.netloc
        ):
            raise RuntimeError(
                "PROPFIND-Antwort verweist auf anderen Server"
            )

    expected_path = unquote(expected.path).rstrip("/")
    returned_path = unquote(returned.path).rstrip("/")

    if returned_path != expected_path:
        raise RuntimeError(
            "PROPFIND-Antwort gehört nicht zum Zielverzeichnis"
        )

    status = item.findtext(
        "d:propstat/d:status",
        namespaces=ns,
    )

    if not status or " 200 " not in status:
        raise RuntimeError(
            "PROPFIND-Eigenschaft nicht erfolgreich"
        )

    collection = item.find(
        "d:propstat/d:prop/d:resourcetype/d:collection",
        ns,
    )

    return collection is not None