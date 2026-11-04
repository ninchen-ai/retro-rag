
"""Nextcloud-Transportadapter für den Review-Workflow."""

from llm_import.nextcloud_review import (
    read_review_file,
    verify_review_directory,
)


class NextcloudReviewTransport:
    """Lesender WebDAV-Adapter; Schreiboperationen gesperrt."""

    def __init__(self, *, base_url, user, password):
        self.connection = {
            "base_url": base_url,
            "user": user,
            "password": password,
        }

    def read(self, path):
        return read_review_file(
            **self.connection,
            path=path,
        )

    def verify_directory(self, path):
        return verify_review_directory(
            **self.connection,
            path=path,
        )

    def create_directory(self, path):
        raise RuntimeError(
            "MKCOL im Nextcloud-Adapter noch nicht freigegeben"
        )

    def upload(self, path, content):
        raise RuntimeError(
            "PUT im Nextcloud-Adapter noch nicht freigegeben"
        )
