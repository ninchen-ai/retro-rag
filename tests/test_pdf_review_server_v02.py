"""Local HTTP review protocol: preview does not write, commit is explicit."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from experiments.pdf_review_server_v02 import ReviewServer
from experiments.pdf_structure_v02_assemble import assemble
from test_pdf_structure_v02 import synthetic_reports

FIXTURE = Path(__file__).resolve().parents[1] / (
    "experiments/fixtures/pdf_document_structure_v0.1_example.json"
)


def sample():
    base = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return assemble(base, *synthetic_reports(base))


def png():
    return (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", 612, 792) + bytes([8, 2, 0, 0, 0])
            + b"fake-rest")


class InteractiveReviewTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        base = Path(self.work.name)
        self.v02 = sample()
        self.original = copy.deepcopy(self.v02)
        self.source_path = base / "structure.json"
        self.png_path = base / "page1.png"
        self.ledger_dir = base / "ledger"
        self.ledger_dir.mkdir()
        self.source_path.write_text(json.dumps(self.v02), encoding="utf-8")
        self.png_path.write_bytes(png())
        self.server = ReviewServer(
            ("127.0.0.1", 0), self.source_path, 1,
            self.png_path, self.ledger_dir,
        )
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.target = self.v02["logical_elements"][0]["logical_id"]
        self.payload = {
            "target_id": self.target, "status": "confirmed",
            "reviewer": "nina", "reason": "original PDF inspected",
            "expected_current": None,
        }

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post(self, path, payload, *, secret=None, origin=None, host=None):
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            f"http://127.0.0.1:{self.port}{path}", data=data,
            headers={
                "Content-Type": "application/json",
                "X-Review-Token": (self.server.secret if secret is None else secret),
                "Origin": (f"http://localhost:{self.port}"
                           if origin is None else origin),
                **({"Host": host} if host is not None else {}),
            }, method="POST",
        )
        try:
            with urlopen(req, timeout=4) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_http_get_html_contains_interactive_form_and_safe_csp(self):
        with urlopen(f"http://localhost:{self.port}/", timeout=4) as response:
            html = response.read().decode("utf-8")
        self.assertIn("Jetzt verbindlich speichern", html)
        self.assertIn("Entscheidung vorbereiten", html)
        self.assertIn("connect-src 'self'", html)
        self.assertIn("preview_token", html)
        self.assertIn("data:image/png;base64,", html)
        self.assertEqual(list(self.ledger_dir.glob("*.json")), [])

    def test_preview_never_creates_record(self):
        status, body = self.post("/api/preview", self.payload)
        self.assertEqual(status, 200)
        self.assertEqual(body["proposal"]["status"], "confirmed")
        self.assertEqual(list(self.ledger_dir.glob("*.json")), [])

    def test_commit_requires_matching_preview_token(self):
        status, body = self.post(
            "/api/commit", {**self.payload, "preview_token": "invalid"}
        )
        self.assertEqual(status, 409)
        self.assertFalse(list(self.ledger_dir.glob("*.json")))

    def test_two_phase_creates_one_record_and_replay_fails(self):
        code, body = self.post("/api/preview", self.payload)
        self.assertEqual(code, 200)
        commit = {**self.payload, "preview_token": body["preview_token"]}
        code, result = self.post("/api/commit", commit)
        self.assertEqual(code, 200)
        self.assertEqual(result["decision"]["target_id"], self.target)
        self.assertEqual(len(list(self.ledger_dir.glob("*.json"))), 1)
        self.assertEqual(self.v02, self.original)
        code, _ = self.post("/api/commit", commit)
        self.assertEqual(code, 409)
        self.assertEqual(len(list(self.ledger_dir.glob("*.json"))), 1)

    def test_modified_details_cannot_be_committed(self):
        _, body = self.post("/api/preview", self.payload)
        code, _ = self.post("/api/commit", {
            **self.payload, "reason": "different",
            "preview_token": body["preview_token"],
        })
        self.assertEqual(code, 409)
        self.assertFalse(list(self.ledger_dir.glob("*.json")))

    def test_changed_target_after_preview_is_rejected(self):
        _, body = self.post("/api/preview", self.payload)
        updated = copy.deepcopy(self.v02)
        updated["logical_elements"][0]["label"] = "changed after preview"
        self.source_path.write_text(json.dumps(updated), encoding="utf-8")
        code, answer = self.post("/api/commit", {
            **self.payload, "preview_token": body["preview_token"],
        })
        self.assertEqual(code, 409)
        self.assertIn("changed", answer["error"])
        self.assertFalse(list(self.ledger_dir.glob("*.json")))

    def test_stale_preview_after_someone_else_commits(self):
        _, first = self.post("/api/preview", self.payload)
        _, second = self.post("/api/preview", self.payload)
        code, _ = self.post("/api/commit", {
            **self.payload, "preview_token": first["preview_token"],
        })
        self.assertEqual(code, 200)
        code, _ = self.post("/api/commit", {
            **self.payload, "preview_token": second["preview_token"],
        })
        self.assertEqual(code, 409)
        self.assertEqual(len(list(self.ledger_dir.glob("*.json"))), 1)

    def test_missing_token_rejected(self):
        code, _ = self.post("/api/preview", self.payload, secret="wrong")
        self.assertEqual(code, 403)

    def test_wrong_origin_rejected(self):
        code, _ = self.post("/api/preview", self.payload,
                            origin="https://malicious.invalid")
        self.assertEqual(code, 403)

    def test_wrong_host_rejected(self):
        code, _ = self.post("/api/preview", self.payload,
                            host=f"malicious.invalid:{self.port}")
        self.assertEqual(code, 403)

    def test_server_rejects_non_loopback_binding(self):
        with self.assertRaisesRegex(ValueError, "127.0.0.1"):
            ReviewServer(("0.0.0.0", 0), self.source_path, 1,
                         self.png_path, self.ledger_dir)

    def test_invalid_target_rejected_without_write(self):
        code, body = self.post("/api/preview", {
            **self.payload, "target_id": "invalid-id"
        })
        self.assertEqual(code, 409)
        self.assertIn("Unknown review target", body["error"])
        self.assertFalse(list(self.ledger_dir.glob("*.json")))

    def test_invalid_json_fields_rejected(self):
        code, _ = self.post("/api/preview", {**self.payload, "unexpected": 1})
        self.assertEqual(code, 409)
        self.assertFalse(list(self.ledger_dir.glob("*.json")))


if __name__ == "__main__":
    unittest.main()
