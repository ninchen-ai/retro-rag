"""Local-only interactive PDF review v0.2, accessed via an SSH tunnel.

Explicit two-phase decisions:
  1) POST /api/preview validates a proposal without writing.
  2) POST /api/commit uses a one-use preview token to append one JSON ledger file.

No PDF/Nextcloud/PostgreSQL writes. No automatic decisions. Never expose
this development server to a public or LAN interface.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time

from experiments.pdf_review_decisions_v02 import apply, inspect_ledger, propose
from experiments.pdf_review_html_v02 import make_html
from experiments.pdf_structure_v02 import validate_v02

MAX_BODY = 4096
PREVIEW_LIFETIME = 600

REVIEW_SECTION = """
<section id="interactive-review" aria-label="Reviewentscheidung vorbereiten">
<h2>Interaktive menschliche Review-Entscheidung</h2>
<div class="panel">
<p class="note">Eine Bestätigung gilt <strong>nur für das ausgewählte Objekt</strong>.
Keine automatische Bestätigung von Nachbarobjekten, Tabellenzellen oder Beziehungen.
Die Quelldaten bleiben unverändert.</p>
<label for="review-target">Review-Objekt</label>
<select id="review-target" style="display:block;width:100%;margin:6px 0 12px;padding:8px"></select>
<label for="review-status">Entscheidung</label>
<select id="review-status" style="display:block;width:100%;margin:6px 0 12px;padding:8px">
<option value="confirmed">Bestätigen</option>
<option value="rejected">Ablehnen</option>
</select>
<label for="review-person">Reviewer</label>
<input id="review-person" type="text" maxlength="120" autocomplete="name"
       style="display:block;width:100%;margin:6px 0 12px;padding:8px" value="nina">
<label for="review-reason">Begründung (erforderlich)</label>
<textarea id="review-reason" rows="3" maxlength="1000"
 style="display:block;width:100%;margin:6px 0 12px;padding:8px"></textarea>
<button type="button" id="review-preview" class="toggle">Entscheidung vorbereiten (ohne Speicherung)</button>
<div id="review-feedback" role="status" aria-live="polite" style="margin:12px 0"></div>
<div id="review-proposal" style="white-space:pre-wrap;overflow-wrap:anywhere"></div>
<button type="button" id="review-commit" class="toggle" disabled>
Jetzt verbindlich speichern
</button>
</div>
</section>
"""

REVIEW_JS = r"""
<script>
"use strict";
(() => {
 const report=JSON.parse(document.getElementById('review-data').textContent);
 const secret=__REVIEW_TOKEN__;
 const target=document.getElementById('review-target');
 const status=document.getElementById('review-status');
 const reviewer=document.getElementById('review-person');
 const reason=document.getElementById('review-reason');
 const previewButton=document.getElementById('review-preview');
 const commitButton=document.getElementById('review-commit');
 const feedback=document.getElementById('review-feedback');
 const output=document.getElementById('review-proposal');
 let pending=null;
 const objects=[
  ...report.regions.map(r=>({id:r.region_id,label:'Region · '+r.region_kind+' · '+r.region_id})),
  ...report.logical_elements.map(l=>({id:l.logical_id,label:'Logisches Element · '+l.label+' · '+l.logical_id})),
  ...report.relationships.map(r=>({id:r.relation_id,label:'Beziehung · '+r.relation_type+' · '+r.relation_id}))
 ];
 const known=new Set(objects.map(o=>o.id));
 for(const obj of objects) {
  const opt=document.createElement('option');
  opt.value=obj.id;opt.textContent=obj.label;
  target.append(opt);
 }
 function invalidate() {
  pending=null;commitButton.disabled=true;output.replaceChildren();
 }
 for(const input of [target,status,reviewer,reason]){
  input.addEventListener('input',invalidate);
  input.addEventListener('change',invalidate);
 }
 function choose(id){
  if(!known.has(id))return;
  target.value=id;invalidate();
  document.getElementById('interactive-review').scrollIntoView({block:'nearest',behavior:'smooth'});
 }
 // The original overlay still highlights/selects its region.
 document.querySelectorAll('#canvas button.region').forEach(btn=>{
  btn.addEventListener('click',()=>choose(btn.title.split(' · ')[0]));
 });
 // Dedicated choices make the logical objects and relations selectable too.
 // Direct actions next to the existing logical-element and relation panels.
 for(const [index,obj] of report.logical_elements.entries()){
  const entry=document.querySelectorAll('#logical .entry')[index];
  if(!entry)continue;
  const button=document.createElement('button');
  button.type='button';button.textContent='Dieses Element prüfen';
  button.addEventListener('click',()=>choose(obj.logical_id));
  entry.append(button);
 }
 for(const [index,obj] of report.relationships.entries()){
  const entry=document.querySelectorAll('#relations .entry')[index];
  if(!entry)continue;
  const button=document.createElement('button');
  button.type='button';button.textContent='Diese Beziehung prüfen';
  button.addEventListener('click',()=>choose(obj.relation_id));
  entry.append(button);
 }
 async function request(path,body){
  const res=await fetch(path,{
   method:'POST',credentials:'same-origin',cache:'no-store',
   headers:{'Content-Type':'application/json','X-Review-Token':secret},
   body:JSON.stringify(body)
  });
  let data;
  try{data=await res.json();}catch{throw new Error('Ungültige Serverantwort');}
  if(!res.ok)throw new Error(data.error||('HTTP '+res.status));
  return data;
 }
 function fields(){
  const current=report.effective_reviews[target.value];
  return {
   target_id:target.value,status:status.value,
   reviewer:reviewer.value.trim(),reason:reason.value.trim(),
   expected_current:current?current.decision_id:null
  };
 }
 previewButton.addEventListener('click',async()=>{
  invalidate();feedback.textContent='Prüfe Vorschlag ...';
  try{
   const payload=fields();
   const response=await request('/api/preview',payload);
   pending={token:response.preview_token,payload};
   output.textContent='Nur Vorschau – noch nicht gespeichert:\n'+
      JSON.stringify(response.proposal,null,2);
   commitButton.disabled=false;
   feedback.textContent='Vorschlag geprüft. Die Speicherung erfordert eine zweite ausdrückliche Aktion.';
  }catch(err){feedback.textContent='Nicht vorbereitet: '+err.message;}
 });
 commitButton.addEventListener('click',async()=>{
  if(!pending)return;
  const active=pending;invalidate();
  if(!window.confirm('Diese Review-Entscheidung als neue JSON-Datei verbindlich speichern?')) {
   feedback.textContent='Abgebrochen. Es wurde nichts gespeichert.';
   return;
  }
  feedback.textContent='Speichere explizite Entscheidung ...';
  try{
   const result=await request('/api/commit',{
    preview_token:active.token,...active.payload
   });
   feedback.textContent='Gespeichert: '+result.decision.decision_id+
     ' · Oberfläche wird aktualisiert.';
   window.location.reload();
  }catch(err){
   feedback.textContent='Nicht gespeichert / Status prüfen: '+err.message+
     '. Bitte die Seite aktualisieren, bevor du erneut entscheidest.';
  }
 });
})();
</script>
"""

def interactive_html(v02, *, page_number, png_bytes, image_name,
                     ledger_dir, secret):
    """Existing HTML unchanged except a local-only interactive UI and CSP."""
    base = make_html(
        v02, page_number=page_number, png_bytes=png_bytes,
        image_name=image_name, ledger_dir=ledger_dir,
    )
    csp = "connect-src 'none'"
    if base.count(csp) != 1 or base.count("</main>") != 1:
        raise ValueError("Unexpected PDF review HTML template")
    return (base.replace(csp, "connect-src 'self'", 1)
            .replace("</main>", REVIEW_SECTION + "\n</main>", 1)
            .replace("</body>", REVIEW_JS.replace(
                "__REVIEW_TOKEN__", json.dumps(secret), 1
            ) + "\n</body>", 1)
            .replace("ausschließlich Vorschau · keine Speicherung von Review-Entscheidungen",
                     "lokaler Reviewserver · Speicherung nur nach expliziter Bestätigung", 1))


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, v02_path, page_number, png_path, ledger_dir):
        if address[0] != "127.0.0.1":
            raise ValueError("For security, the server only binds to 127.0.0.1")
        self.v02_path = Path(v02_path)
        self.png_path = Path(png_path)
        self.ledger_dir = Path(ledger_dir)
        self.page_number = page_number
        self.secret = secrets.token_urlsafe(32)
        self.pending = {}
        self.pending_lock = threading.Lock()
        super().__init__(address, ReviewHandler)

    def source(self):
        data = json.loads(self.v02_path.read_text(encoding="utf-8"))
        errors = validate_v02(data)
        if errors:
            raise ValueError("Invalid v0.2 source: " + "; ".join(errors[:3]))
        return data


class ReviewHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, status, data, content_type="application/json; charset=utf-8"):
        raw = data if isinstance(data, bytes) else json.dumps(
            data, ensure_ascii=False
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(raw)

    def _authorized_host(self):
        return self.headers.get("Host") in {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }

    def do_GET(self):
        if not self._authorized_host():
            return self._respond(403, {"error": "Host rejected"})
        if self.path != "/":
            return self._respond(404, {"error": "Not found"})
        try:
            data = self.server.source()
            html = interactive_html(
                data, page_number=self.server.page_number,
                png_bytes=self.server.png_path.read_bytes(),
                image_name=self.server.png_path.name,
                ledger_dir=self.server.ledger_dir,
                secret=self.server.secret,
            )
        except (ValueError, OSError, KeyError) as exc:
            return self._respond(500, {"error": str(exc)})
        self._respond(200, html.encode("utf-8"),
                      "text/html; charset=utf-8")

    def do_POST(self):
        if not self._authorized_host():
            return self._respond(403, {"error": "Host rejected"})
        if self.path not in ("/api/preview", "/api/commit"):
            return self._respond(404, {"error": "Not found"})
        origin = self.headers.get("Origin")
        if origin not in {
            f"http://localhost:{self.server.server_port}",
            f"http://127.0.0.1:{self.server.server_port}",
        }:
            return self._respond(403, {"error": "Origin rejected"})
        if self.headers.get("X-Review-Token") != self.server.secret:
            return self._respond(403, {"error": "Review token rejected"})
        if self.headers.get("Content-Type") != "application/json":
            return self._respond(415, {"error": "Expected application/json"})
        try:
            size = int(self.headers.get("Content-Length", ""))
            if size < 2 or size > MAX_BODY:
                return self._respond(413, {"error": "Invalid payload size"})
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict):
                raise ValueError("Expected JSON object")
            required = {"target_id", "status", "reviewer",
                        "reason", "expected_current"}
            extra = {"preview_token"} if self.path == "/api/commit" else set()
            if set(body) != required | extra:
                raise ValueError("Unexpected or missing request fields")
            if any(not isinstance(body[k], str) for k in (
                "target_id", "status", "reviewer", "reason"
            )):
                raise ValueError("Invalid request field type")
            if len(body["reviewer"]) > 120 or len(body["reason"]) > 1000:
                raise ValueError("Reviewer/reason too long")
            if body["expected_current"] is not None and not isinstance(
                body["expected_current"], str
            ):
                raise ValueError("Invalid predecessor")
            arguments = {key: body[key] for key in required}
            v02 = self.server.source()
            if self.path == "/api/preview":
                proposal = propose(v02, self.server.ledger_dir, **arguments)
                token = secrets.token_urlsafe(32)
                with self.server.pending_lock:
                    now = time.monotonic()
                    self.server.pending = {
                        k: v for k, v in self.server.pending.items()
                        if v["expires"] > now
                    }
                    self.server.pending[token] = {
                        "payload": arguments, "proposal": proposal,
                        "expires": now + PREVIEW_LIFETIME,
                    }
                return self._respond(200, {
                    "proposal": proposal, "preview_token": token,
                })
            token = body["preview_token"]
            if not isinstance(token, str):
                raise ValueError("Invalid preview token")
            with self.server.pending_lock:
                pending = self.server.pending.pop(token, None)
            if (pending is None or pending["expires"] < time.monotonic()
                    or pending["payload"] != arguments):
                return self._respond(
                    409, {"error": "No valid matching preview; please restart"}
                )
            # Reject changed PDF snapshots and changed target objects even if
            # their review history is still empty. A fresh preview is required.
            refreshed = propose(v02, self.server.ledger_dir, **arguments)
            for field in ("document_sha256", "source_v01_sha256",
                          "target_id", "target_sha256"):
                if refreshed[field] != pending["proposal"][field]:
                    raise ValueError("Source/target changed since preview")
            # Explicit action only. apply() locks and re-checks the current
            # head before creating an independent immutable JSON record.
            record = apply(v02, self.server.ledger_dir, **arguments)
            return self._respond(200, {"decision": record})
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return self._respond(409, {"error": str(exc)})
        except OSError as exc:
            return self._respond(500, {"error": str(exc)})

    def log_message(self, format, *args):
        # Do not log PDF data or reviewer reasons.
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-json", required=True, type=Path)
    parser.add_argument("--page", required=True, type=int)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1-65535")
    if not args.ledger_dir.exists() or not args.ledger_dir.is_dir():
        parser.error("Ledger directory must already exist")
    if args.ledger_dir.is_symlink():
        parser.error("Ledger directory must not be a symlink")
    server = ReviewServer(
        ("127.0.0.1", args.port), args.v02_json, args.page,
        args.image, args.ledger_dir,
    )
    # Validate all inputs before announcing the server as ready.
    interactive_html(
        server.source(), page_number=args.page,
        png_bytes=args.image.read_bytes(), image_name=args.image.name,
        ledger_dir=args.ledger_dir, secret=server.secret,
    )
    print(f"PDF Review (nur localhost): http://127.0.0.1:{args.port}/",
          flush=True)
    print("Verwende einen SSH-Tunnel von Iris; keine öffentliche Freigabe.",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReviewserver beendet.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
