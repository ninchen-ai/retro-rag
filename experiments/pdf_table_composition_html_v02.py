"""HTML panel for reviewed horizontal continuation proposal (no data editing)."""
from __future__ import annotations

import html
import json

from experiments.pdf_review_html_v02 import _escape_script_json


def composition_panel(proposal, current, secret, original_regions=None):
    """Embed evidence and derived preview safely in the existing review page."""
    rows = proposal["preview_rows"]
    source_ids = proposal["source_region_ids"]
    cells = [row["cells"] for row in rows]
    if not cells:
        raise ValueError("Empty composition preview")
    columns = len(cells[0])
    header = "".join("<th>" + html.escape("" if c is None else c)
                     + "</th>" for c in cells[0])
    body = []
    for row in rows[1:]:
        items = "".join("<td>" + html.escape("" if c is None else c)
                        + "</td>" for c in row["cells"])
        prov = html.escape(f'{row["region_id"]} · source row {row["row_index"] + 1}')
        body.append("<tr title='" + prov + "'>" + items + "</tr>")
    originals = []
    original_regions = original_regions or {}
    for rid in source_ids:
        region = original_regions.get(rid)
        if region is None or "raw_cells" not in region:
            raise ValueError("Missing original PyMuPDF matrix")
        original_rows = []
        for original_row in region["raw_cells"]:
            items = "".join(
                "<td>" + html.escape("" if cell is None else cell) + "</td>"
                for cell in original_row
            )
            original_rows.append("<tr>" + items + "</tr>")
        originals.append(
            '<div style="flex:1;min-width:260px"><strong>' +
            html.escape(rid) +
            '</strong><div class="tablewrap"><table>' +
            "".join(original_rows) + "</table></div></div>"
        )
    originals_html = (
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin:12px 0">' +
        "".join(originals) + "</div>"
    )
    data = {
        "proposal": proposal,
        "current": current,
    }
    payload = _escape_script_json(data)
    safe_title = html.escape(proposal["logical_label"])
    safe_ids = html.escape(" → ".join(source_ids))
    excluded = ", ".join(
        f'{e["region_id"]} row {e["row_index"]+1} ({e["reason"]})'
        for e in proposal["preview_excluded_rows"]
    ) or "none"
    return ("""
<section id="composition-review">
<h2>Tabellen-Zusammensetzung: getrennt prüfbarer Vorschlag</h2>
<div class="panel">
<p><strong>""" + safe_title + """</strong></p>
<p>Quelle / Reihenfolge: <code>""" + safe_ids + """</code></p>
<p><strong>Unveränderte Originalmatrizen nebeneinander:</strong></p>""" +
            originals_html + """
<p><strong>Vorgeschlagene logische Darstellung:</strong> """ +
            str(len(rows) - 1) + " Datenzeilen × " + str(columns) +
            """ Spalten (fortlaufende Blöcke, nicht nebeneinander verschmolzene Spalten).</p>
<div class="tablewrap"><table><thead><tr>""" + header +
            "</tr></thead><tbody>" + "".join(body) + """</tbody></table></div>
<p><small>Zeilen aus der Vorschau ausgelassen (in original raw_cells weiterhin vollständig vorhanden):
""" + html.escape(excluded) + """</small></p>
<p class="note">Nur ein Vorschlag. Die bisherigen Table-5- und Regionen-Bestätigungen
bestätigen <strong>nicht</strong> diese Komposition. Keine automatische RAG-Freigabe.</p>
<div id="composition-current" class="review-status"></div>
<label for="composition-status">Entscheidung zur gesamten Zusammensetzung</label>
<select id="composition-status" style="display:block;width:100%;padding:8px;margin:6px 0 12px">
<option value="confirmed">Zusammensetzung bestätigen</option>
<option value="rejected">Zusammensetzung ablehnen</option>
</select>
<label for="composition-person">Reviewer</label>
<input id="composition-person" type="text" maxlength="120" value="nina"
style="display:block;width:100%;padding:8px;margin:6px 0 12px">
<label for="composition-reason">Begründung (erforderlich)</label>
<textarea id="composition-reason" maxlength="1000" rows="3"
style="display:block;width:100%;padding:8px;margin:6px 0 12px"></textarea>
<button type="button" id="composition-preview" class="toggle">Tabellenentscheidung vorbereiten (ohne Speichern)</button>
<pre id="composition-preview-output"></pre>
<div id="composition-feedback" role="status" aria-live="polite"></div>
<button type="button" class="toggle" id="composition-commit" disabled>Tabellenentscheidung verbindlich speichern</button>
</div>
<script type="application/json" id="composition-data">""" + payload + """</script>
</section>
<script>
"use strict";
(()=>{
 const data=JSON.parse(document.getElementById("composition-data").textContent);
 const secret=__TOKEN__;
 const status=document.getElementById("composition-status");
 const reviewer=document.getElementById("composition-person");
 const reason=document.getElementById("composition-reason");
 const prepare=document.getElementById("composition-preview");
 const save=document.getElementById("composition-commit");
 const output=document.getElementById("composition-preview-output");
 const feedback=document.getElementById("composition-feedback");
 const current=document.getElementById("composition-current");
 current.textContent=data.current?
   "Bisherige explizite Entscheidung: "+data.current.status+" · "+data.current.decision_id:
   "Noch keine Entscheidung zur Komposition";
 let pending=null;
 const invalidate=()=>{pending=null;save.disabled=true;output.textContent="";};
 for(const field of [status,reviewer,reason]){
  field.addEventListener("input",invalidate);
  field.addEventListener("change",invalidate);
 }
 const fields=()=>({
  status:status.value,reviewer:reviewer.value.trim(),
  reason:reason.value.trim(),
  expected_current:data.current?data.current.decision_id:null,
  proposal_id:data.proposal.proposal_id
 });
 async function request(path,body){
  const response=await fetch(path,{
   method:"POST",cache:"no-store",credentials:"same-origin",
   headers:{"Content-Type":"application/json","X-Review-Token":secret},
   body:JSON.stringify(body)
  });
  let message;
  try { message=await response.json(); }
  catch { throw new Error("Serverantwort nicht lesbar"); }
  if(!response.ok)throw new Error(message.error || "HTTP "+response.status);
  return message;
 }
 prepare.addEventListener("click",async()=>{
  invalidate();feedback.textContent="Prüfe Tabellen-Zusammensetzung ...";
  try{
   const payload=fields();
   const result=await request("/api/composition/preview",payload);
   pending={payload,token:result.preview_token};
   output.textContent="NOCH NICHT GESPEICHERT:\n"+JSON.stringify(result.proposal,null,2);
   feedback.textContent="Vorschlag geprüft. Speichern nur nach zusätzlicher Bestätigung.";
   save.disabled=false;
  }catch(err){feedback.textContent="Nicht vorbereitet: "+err.message;}
 });
 save.addEventListener("click",async()=>{
  if(!pending)return;
  const p=pending;invalidate();
  if(!window.confirm("Diese Tabellen-ZUSAMMENSETZUNG ausdrücklich speichern?")){
   feedback.textContent="Abgebrochen – keine Speicherung.";
   return;
  }
  feedback.textContent="Speichere Entscheidung ...";
  try{
   const result=await request("/api/composition/commit",{
    ...p.payload,preview_token:p.token,
   });
   feedback.textContent="Gespeichert: "+result.decision.decision_id;
   window.location.reload();
  }catch(err){
   feedback.textContent="Nicht gespeichert / Zustand prüfen: "+err.message;
  }
 });
})();
</script>
""").replace("__TOKEN__", json.dumps(secret), 1)
