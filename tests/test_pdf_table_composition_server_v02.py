"""End-to-end HTTP tests for interactive split-table composition decisions."""
import json
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from experiments.pdf_review_server_v02 import ReviewServer
from experiments.pdf_table_composition_v02 import propose_composition
from test_pdf_table_composition_v02 import fixture


class CompositionServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.v02, logical, regions = fixture()
        self.proposal = propose_composition(
            self.v02, logical_id=logical, source_region_ids=regions
        )
        self.v02file = folder / "v02.json"
        self.png = folder / "page1.png"
        self.proposalfile = folder / "composition.json"
        self.baseledger = folder / "reviews"
        self.compledger = folder / "compositions"
        self.baseledger.mkdir()
        self.compledger.mkdir()
        self.v02file.write_text(json.dumps(self.v02), encoding="utf-8")
        self.proposalfile.write_text(json.dumps(self.proposal), encoding="utf-8")
        self.png.write_bytes(
            b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR"
            + struct.pack(">II", 612, 792) + bytes([8, 2, 0, 0, 0])
            + b"fake-rest"
        )
        self.server = ReviewServer(
            ("127.0.0.1", 0), self.v02file, 1, self.png,
            self.baseledger, composition_path=self.proposalfile,
            composition_ledger_dir=self.compledger,
        )
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.addCleanup(self.close)
        self.port = self.server.server_port
        self.args = {
            "proposal_id": self.proposal["proposal_id"],
            "status": "confirmed", "reviewer": "nina",
            "reason": "same table, continued on right",
            "expected_current": None,
        }

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post(self, path, data):
        raw = json.dumps(data).encode("utf-8")
        request = Request(
            f"http://127.0.0.1:{self.port}{path}", data=raw,
            headers={
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
                "X-Review-Token": self.server.secret,
            }, method="POST",
        )
        try:
            with urlopen(request, timeout=4) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_html_shows_composition_with_evidence_and_explicit_controls(self):
        with urlopen(f"http://127.0.0.1:{self.port}/", timeout=4) as response:
            markup = response.read().decode("utf-8")
        self.assertIn("Tabellen-Zusammensetzung", markup)
        self.assertIn("source row", markup)
        self.assertIn("Tabellenentscheidung verbindlich speichern", markup)
        self.assertIn("repeated_header", markup)
        # A Python triple-quoted HTML template must escape JS newlines:
        # a literal line break inside a JS double-quoted string stops the
        # whole composition script, leaving the Prepare button inert.
        self.assertIn(r'NOCH NICHT GESPEICHERT:\n', markup)
        self.assertNotIn('NOCH NICHT GESPEICHERT:\n', markup)
        self.assertFalse(list(self.compledger.glob("*.json")))

    def test_preview_only_then_explicit_commit(self):
        code, preview = self.post("/api/composition/preview", self.args)
        self.assertEqual(code, 200)
        self.assertFalse(list(self.compledger.glob("*.json")))
        code, result = self.post("/api/composition/commit", {
            **self.args, "preview_token": preview["preview_token"],
        })
        self.assertEqual(code, 200)
        self.assertEqual(result["decision"]["status"], "confirmed")
        self.assertEqual(len(list(self.compledger.glob("*.json"))), 1)
        self.assertFalse(list(self.baseledger.glob("*.json")))
        self.assertEqual(
            json.loads(self.v02file.read_text(encoding="utf-8")),
            self.v02,
        )

    def test_commit_without_preview_rejected(self):
        code, _ = self.post("/api/composition/commit", {
            **self.args, "preview_token": "fake",
        })
        self.assertEqual(code, 409)
        self.assertFalse(list(self.compledger.glob("*.json")))

    def test_stale_proposal_rejected_before_commit(self):
        _, response = self.post("/api/composition/preview", self.args)
        changed = json.loads(self.proposalfile.read_text(encoding="utf-8"))
        changed["preview_rows"][-1]["cells"][1] = "tampered"
        self.proposalfile.write_text(json.dumps(changed), encoding="utf-8")
        code, _ = self.post("/api/composition/commit", {
            **self.args, "preview_token": response["preview_token"],
        })
        self.assertEqual(code, 409)
        self.assertFalse(list(self.compledger.glob("*.json")))


if __name__ == "__main__":
    unittest.main()
