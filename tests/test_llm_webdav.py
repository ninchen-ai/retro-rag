import unittest
from unittest.mock import patch

from llm_import.webdav import list_inbox_documents


DAV_RESPONSE = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/nina/Retro-Computing/Import/inbox/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>

  <d:response>
    <d:href>/remote.php/dav/files/nina/Retro-Computing/Import/inbox/Rade9200.pdf</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype/>
        <d:getcontentlength>626849</d:getcontentlength>
        <d:getetag>"test-etag"</d:getetag>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>
"""


class FakeResponse:
    status = 207

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size=-1):
        return DAV_RESPONSE


class TestWebDAVInbox(unittest.TestCase):

    @patch("llm_import.webdav.urlopen")
    def test_list_inbox_documents(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse()

        documents = list_inbox_documents(
            url="http://127.0.0.1:8080",
            user="nina",
            password="test-password",
        )

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["filename"], "Rade9200.pdf")
        self.assertEqual(documents[0]["size"], 626849)
        self.assertEqual(documents[0]["etag"], '"test-etag"')

        request = mock_urlopen.call_args.args[0]

        self.assertEqual(request.get_method(), "PROPFIND")
        self.assertEqual(request.get_header("Depth"), "1")

    def test_reject_remote_http(self):
        with self.assertRaises(ValueError):
            list_inbox_documents(
                url="http://example.com",
                user="nina",
                password="test-password",
            )


if __name__ == "__main__":
    unittest.main()