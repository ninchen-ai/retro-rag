"""Read-only WebDAV adapter for the Retro-RAG import inbox."""

import base64
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


DAV = {
    "d": "DAV:",
}

PROPFIND_BODY = b"""<?xml version="1.0"?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:resourcetype/>
    <d:getcontentlength/>
    <d:getetag/>
  </d:prop>
</d:propfind>
"""


def list_inbox_documents(
    url: str,
    user: str,
    password: str,
    folder: str = "Retro-Computing/Import/inbox",
) -> list[dict]:
    """List direct files in a Nextcloud inbox without modifying anything."""

    parsed = urlsplit(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ungültiges URL-Schema")

    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        raise ValueError("HTTP ist nur über localhost erlaubt")

    base = url.rstrip("/")

    prefix = (
        "/remote.php/dav/files/"
        + quote(user, safe="")
        + "/"
        + quote(folder.strip("/"), safe="/")
        + "/"
    )

    authorization = base64.b64encode(
        f"{user}:{password}".encode("utf-8")
    ).decode("ascii")

    request = Request(
        base + prefix,
        data=PROPFIND_BODY,
        method="PROPFIND",
        headers={
            "Authorization": "Basic " + authorization,
            "Depth": "1",
            "Content-Type": "application/xml",
        },
    )

    with urlopen(request, timeout=30) as response:
        if response.status != 207:
            raise RuntimeError(
                f"Unerwarteter WebDAV-Status: {response.status}"
            )

        xml_bytes = response.read(2 * 1024 * 1024 + 1)

    if len(xml_bytes) > 2 * 1024 * 1024:
        raise ValueError("WebDAV-Verzeichnisantwort zu groß")

    root = ET.fromstring(xml_bytes)

    if root.tag != "{DAV:}multistatus":
        raise ValueError("Ungültige WebDAV-Verzeichnisantwort")

    documents = []

    for item in root.findall("d:response", DAV):
        href = item.findtext("d:href", namespaces=DAV)

        if not href:
            continue

        item_path = unquote(urlsplit(href).path)
        root_path = unquote(prefix)

        if item_path.rstrip("/") == root_path.rstrip("/"):
            continue

        if not item_path.startswith(root_path):
            raise ValueError("WebDAV-Pfad außerhalb der Inbox")

        relative = item_path[len(root_path):].strip("/")

        # Only immediate children of the inbox.
        if not relative or "/" in relative:
            continue

        is_directory = item.find(
            ".//d:resourcetype/d:collection",
            DAV,
        ) is not None

        if is_directory:
            continue

        size_text = item.findtext(
            ".//d:getcontentlength",
            namespaces=DAV,
        )

        if size_text is None or not size_text.isdecimal():
            raise ValueError(f"Ungültige Dateigröße: {relative}")

        etag = item.findtext(
            ".//d:getetag",
            namespaces=DAV,
        )

        documents.append(
            {
                "filename": relative,
                "size": int(size_text),
                "etag": etag,
                "path": folder.strip("/") + "/" + relative,
            }
        )

    return sorted(documents, key=lambda entry: entry["filename"])

def download_inbox_document(
    url: str,
    user: str,
    password: str,
    document: dict,
    folder: str = "Retro-Computing/Import/inbox",
    max_bytes: int = 50 * 1024 * 1024,
) -> bytes:
    """Download a listed inbox document into memory, read-only."""

    from urllib.error import HTTPError

    filename = document["filename"]

    if (
        not isinstance(filename, str)
        or not filename
        or filename in (".", "..")
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise ValueError("Ungültiger Dateiname")

    if not filename.lower().endswith((".txt", ".md", ".pdf")):
        raise ValueError("Nicht unterstütztes Dateiformat")

    if max_bytes <= 0:
        raise ValueError("Ungültige Größenbegrenzung")

    size = document["size"]

    if type(size) is not int or size < 0 or size > max_bytes:
        raise ValueError("Dateigröße ungültig oder zu groß")

    parsed = urlsplit(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ungültiges URL-Schema")

    if parsed.scheme == "http" and parsed.hostname not in (
        "localhost", "127.0.0.1", "::1"
    ):
        raise ValueError("HTTP ist nur über localhost erlaubt")

    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("URL darf keine Zugangsdaten oder Parameter enthalten")

    prefix = (
        "/remote.php/dav/files/"
        + quote(user, safe="")
        + "/"
        + quote(folder.strip("/"), safe="/")
        + "/"
    )

    path = prefix + quote(filename, safe="")

    authorization = base64.b64encode(
        f"{user}:{password}".encode("utf-8")
    ).decode("ascii")

    headers = {
        "Authorization": "Basic " + authorization,
    }

    etag = document.get("etag")

    if etag:
        headers["If-Match"] = etag

    request = Request(
        url.rstrip("/") + path,
        headers=headers,
        method="GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Unerwarteter Download-Status: {response.status}"
                )

            data = response.read(max_bytes + 1)

    except HTTPError as exc:
        if exc.code == 412:
            raise ValueError(
                "Datei wurde seit der Auflistung verändert"
            ) from exc
        raise

    if len(data) > max_bytes:
        raise ValueError("Download überschreitet Größenbegrenzung")

    if len(data) != size:
        raise ValueError(
            "Downloadgröße weicht von der Verzeichnisangabe ab"
        )

    return data