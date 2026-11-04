
"""Schreibtransport für Review-Dateien.

Schreibfunktionen werden ausschließlich über explizit
injizierte Funktionen bereitgestellt.

Es gibt keine automatische Verbindung zu produktiven
WebDAV-Schreiboperationen.
"""

from llm_import.review_transport import NextcloudReviewTransport


class NextcloudReviewWriteTransport(NextcloudReviewTransport):

    def __init__(
        self,
        *,
        base_url,
        user,
        password,
        mkcol,
        put,
    ):
        super().__init__(
            base_url=base_url,
            user=user,
            password=password,
        )

        if not callable(mkcol) or not callable(put):
            raise TypeError(
                "MKCOL und PUT benötigen explizite Funktionen"
            )

        self._mkcol = mkcol
        self._put = put

    def create_directory(self, path):
        result = self._mkcol(
            **self.connection,
            path=path,
        )

        if not isinstance(result, dict):
            raise RuntimeError("Ungültige MKCOL-Antwort")

        status = result.get("status")

        if status not in {"CREATED", "EXISTS"}:
            raise RuntimeError(
                f"MKCOL fehlgeschlagen: {status}"
            )

        return status

    def upload(self, path, content):
        if not isinstance(content, bytes):
            raise TypeError("Upload-Inhalt muss bytes sein")

        text = content.decode("utf-8")

        result = self._put(
            **self.connection,
            path=path,
            content=text,
        )

        if not isinstance(result, dict):
            raise RuntimeError("Ungültige PUT-Antwort")

        status = result.get("status")

        if status != "CREATED":
            raise RuntimeError(
                f"PUT nicht bestätigt: {status}"
            )

        return status
