
"""Manueller Nextcloud-WebDAV-Schreibtest.

Erstellt ein isoliertes Testverzeichnis und prüft
MKCOL, PUT, GET und HTTP 412.
"""

from getpass import getpass
from hashlib import sha256
from uuid import uuid4

from llm_import.nextcloud_review import (
    verify_review_directory,
    create_review_directory,
    upload_review_file,
    read_review_file,
)


def main():
    connection = {
        "base_url": "http://127.0.0.1:8080",
        "user": "nina",
        "password": getpass("Nextcloud-App-Passwort: "),
    }

    root = "Retro-Computing/Import/review/"
    test_id = uuid4().hex[:16]
    directory = f"{root}integration-test-{test_id}/"
    path = directory + "test.md"

    content = (
        "# Retro-RAG WebDAV-Test\n\n"
        f"Test-ID: {test_id}\n"
    )

    print("Testverzeichnis:", directory)

    assert verify_review_directory(**connection, path=root)
    print("PROPFIND: OK")

    result = create_review_directory(
        **connection,
        path=directory,
    )
    assert result["status"] == "CREATED"
    print("MKCOL: CREATED")

    result = upload_review_file(
        **connection,
        path=path,
        content=content,
    )
    assert result["status"] == "CREATED"
    print("PUT: CREATED")

    remote = read_review_file(
        **connection,
        path=path,
    )
    assert remote == content.encode("utf-8")
    print("GET: OK")
    print("SHA-256:", sha256(remote).hexdigest())

    result = upload_review_file(
        **connection,
        path=path,
        content="# Überschreibversuch\n",
    )

    assert result["status"] == "CONFLICT"
    assert result["http_status"] == 412
    print("Zweiter PUT: HTTP 412 / CONFLICT")

    remote_after = read_review_file(
        **connection,
        path=path,
    )
    assert remote_after == content.encode("utf-8")

    print("Originalinhalt unverändert: OK")
    print("INTEGRATIONSTEST ERFOLGREICH")


if __name__ == "__main__":
    main()
