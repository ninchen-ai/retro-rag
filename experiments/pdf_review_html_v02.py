"""Generate a self-contained, local, read-only PDF v0.2 review HTML.

A selected PDF page PNG is embedded as a data URI. All coordinates are
the ORIGINAL v0.2 PDF point rectangles. No web server, DB, external assets,
network requests, automatic approvals, or writes to input files.
"""
from __future__ import annotations

import argparse
import base64
import copy
import html
import json
from pathlib import Path
import struct

from experiments.pdf_structure_v02 import validate_v02


def png_dimensions(raw):
    """PNG dimensions from the header; image decoding is delegated to browser."""
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("Expected a valid PNG header")
    width, height = struct.unpack(">II", raw[16:24])
    if width <= 0 or height <= 0:
        raise ValueError("Invalid PNG image dimensions")
    return width, height


def page_review_data(data, *, page_number, image_name, image_dimensions):
    """Extract a single page's small subset, never exposing all v0.1 spans."""
    problems = validate_v02(data)
    if problems:
        raise ValueError("Invalid v0.2: " + "; ".join(problems[:5]))
    base = data["source_v01"]
    if not 1 <= page_number <= len(base["pages"]):
        raise ValueError("Invalid PDF page number")
    page = base["pages"][page_number - 1]
    if page["page_number"] != page_number or page["rotation"] != 0:
        raise ValueError("Page metadata mismatch; rotated PDF pages unsupported")

    run_ids = set()
    image_matches = []
    for run in data["processing_runs"]:
        if run["parameters"].get("page") == page_number:
            run_ids.add(run["run_id"])
            if run["method"] == "doclayout_yolo":
                image_matches.append(run)
    if len(image_matches) != 1:
        raise ValueError("Expected exactly one layout run for selected page")
    layout_params = image_matches[0]["parameters"]
    if layout_params.get("image_name") != image_name:
        raise ValueError("PNG filename differs from recorded layout source image")
    if layout_params.get("image_size_pixels") != list(image_dimensions):
        raise ValueError("PNG dimensions differ from recorded layout geometry")

    regions = [
        copy.deepcopy(r) for r in data["physical_regions"]
        if r["page_number"] == page_number
    ]
    region_ids = {r["region_id"] for r in regions}
    logical_all = {v["logical_id"]: v for v in data["logical_elements"]}
    # Pick only logical elements that refer to on-page regions, including captions.
    relationships = data["relationships_v02"]
    logical_ids = {
        rel["from_id"] for rel in relationships
        if rel["to_id"] in region_ids and rel["from_id"] in logical_all
    }
    logical = [
        copy.deepcopy(x) for x in data["logical_elements"]
        if x["logical_id"] in logical_ids
    ]
    selected = region_ids | logical_ids
    relations = [
        copy.deepcopy(r) for r in relationships
        if r["from_id"] in selected and r["to_id"] in selected
    ]
    relation_ids = {r["relation_id"] for r in relations}
    selected |= relation_ids
    decisions = [
        copy.deepcopy(x) for x in data["review_decisions"]
        if x["target_id"] in selected
    ]
    return {
        "page_number": page_number,
        "document": base["document"].get("filename") or
                    Path(base["document"]["source_uri"]).name,
        "document_sha256": base["document"]["sha256"],
        "source_v01_sha256": data["source_v01_sha256"],
        "page_size_pt": [page["width_pt"], page["height_pt"]],
        "image_size_pixels": list(image_dimensions),
        "regions": regions,
        "logical_elements": logical,
        "relationships": relations,
        "review_decisions": decisions,
        "review_status": data["quality_v02"]["status"],
    }


def _escape_script_json(value):
    # json.dumps by itself is unsafe inside a script tag (literal </script>).
    # Encoding HTML-sensitive characters also prevents HTML injection in
    # text originated in PDF extraction and metadata.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "&", "\\u0026"
    ).replace("<", "\\u003c").replace(">", "\\u003e").replace(
        "\u2028", "\\u2028"
    ).replace("\u2029", "\\u2029")


def make_html(data, *, page_number, png_bytes, image_name):
    dims = png_dimensions(png_bytes)
    review = page_review_data(
        data, page_number=page_number, image_name=image_name,
        image_dimensions=dims,
    )
    payload = _escape_script_json(review)
    image_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
    heading = html.escape(review["document"], quote=True)
    # Only local, embedded static assets. JS changes selection/highlighting
    # in the browser; it never writes review decisions to disk.
    return """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'">
<title>Retro-RAG PDF Review – """ + heading + """</title>
<style>
:root {color-scheme:light; font-family:system-ui,Arial,sans-serif; color:#1b2934; background:#f0f3f7}
* {box-sizing:border-box} body{margin:0} header{background:#132d42;color:white;padding:16px 24px}
header h1{font-size:1.25rem;margin:0 0 5px} header p{margin:0;font-size:.86rem;color:#dce8f3}
main{display:grid;grid-template-columns:minmax(340px,1.1fr) minmax(340px,1fr);gap:16px;padding:16px;align-items:start}
section{min-width:0;background:#fff;border:1px solid #d4dce4;border-radius:10px;overflow:hidden}
section h2{margin:0;padding:12px 16px;font-size:1rem;background:#edf2f7}
#page-pane{padding:12px;max-height:85vh;overflow:auto;background:#dae1e8}
#canvas{position:relative;margin:0 auto;width:100%;max-width:950px}
#canvas img{display:block;width:100%;height:auto}
.region{position:absolute;border:2px solid;cursor:pointer;background:transparent;
 padding:0;min-width:1px;min-height:1px}
.region.table{border-color:#07936f;background:rgba(0,180,120,.07)}
.region.figure{border-color:#a354d9;background:rgba(150,80,220,.06)}
.region.caption{border-color:#2279d7;background:rgba(40,110,240,.08)}
.region.other,.region.diagram{border-color:#c67c16;background:rgba(240,140,30,.05)}
.region.selected{outline:3px solid #e63c30;z-index:10;background:rgba(255,220,0,.18)}
.region:focus-visible{outline:3px solid #000;z-index:11}
.panel{padding:12px 16px;border-top:1px solid #e1e7ee}
small,.muted{color:#55687a} .summary{display:flex;flex-wrap:wrap;gap:10px}
.chip{font-size:.78rem;background:#eaf0f6;padding:4px 9px;border-radius:16px}
button.toggle{border:1px solid #8296a9;border-radius:7px;padding:6px 10px;background:white;cursor:pointer;margin:3px}
button.toggle[aria-pressed="false"]{opacity:.45}
.entry{padding:9px;border:1px solid #d9e1e9;border-radius:8px;margin:7px 0}
.entry strong{overflow-wrap:anywhere} .entry button{background:#f0f5fa;border:0;padding:6px;cursor:pointer;text-align:left;width:100%}
pre{font-family:ui-monospace,monospace;font-size:.78rem;white-space:pre-wrap;overflow-wrap:anywhere}
.tablewrap{max-height:320px;overflow:auto;border:1px solid #d8e0e8}
table{border-collapse:collapse;font-size:.83rem}th,td{border:1px solid #cbd5df;padding:6px;vertical-align:top;white-space:pre-wrap;min-width:50px}
th{background:#e9eff4;position:sticky;top:0} code{overflow-wrap:anywhere}
.note{padding:9px;border-left:4px solid #b36a00;background:#fff3df}
@media(max-width:950px){main{grid-template-columns:1fr}#page-pane{max-height:65vh}}
</style>
</head>
<body>
<header><h1>Retro-RAG PDF Review – """ + heading + """</h1>
<p>Seite """ + str(page_number) + """ · ausschließlich Vorschau · keine Speicherung von Review-Entscheidungen</p></header>
<main>
<section><h2>Originalseitenbild mit erkannten Regionen</h2>
<div class="panel" id="filters"></div>
<div id="page-pane"><div id="canvas"><img alt="Originale PDF-Seite" src=\"""" + image_uri + """\"></div></div>
<div class="panel muted">Rahmen sind Erkennungsvorschläge und können überlappen. Das PNG ist eine
Darstellung der Quellseite, nicht das Original-PDF selbst.</div></section>
<section><h2>Extraktionen, Beziehungen und Review</h2>
<div class="panel" id="summary"></div>
<div class="panel"><strong>Ausgewählte Region</strong><div id="selection" class="muted">Region anklicken.</div></div>
<div class="panel"><strong>Logische Elemente</strong><div id="logical"></div></div>
<div class="panel"><strong>Tabellenmatrizen (unverändert)</strong><div id="matrices"></div></div>
<div class="panel"><strong>Beziehungen und Konflikte</strong><div id="relations"></div></div>
<div class="panel"><strong>Bestehende Review-Entscheidungen (nur Anzeige)</strong><div id="decisions"></div></div>
<div class="panel note">Keine automatische Bestätigung. Fehlende Konfliktmeldungen
beweisen keine fachliche Korrektheit. Bitte mit dem Original-PDF abgleichen.</div>
</section>
</main>
<script type="application/json" id="review-data">""" + payload + """</script>
<script>
"use strict";
const report=JSON.parse(document.getElementById('review-data').textContent);
const el=(tag,content,klass)=>{const x=document.createElement(tag);if(content!==undefined)x.textContent=String(content);if(klass)x.className=klass;return x};
const add=(parent,tag,content,klass)=>{const x=el(tag,content,klass);parent.append(x);return x};
const canvas=document.getElementById('canvas'),selection=document.getElementById('selection');
const regions=new Map(),buttons=new Map(),visible=new Map();
for(const r of report.regions){
 const type=r.region_kind;
 const b=r.bbox_pt, [w,h]=report.page_size_pt;
 const btn=el('button',undefined,'region '+(type==='table'||type==='figure'||type==='caption'||type==='diagram'?type:'other'));
 btn.type='button'; btn.title=r.region_id+' · '+type;
 btn.setAttribute('aria-label',btn.title);
 btn.style.left=(100*b[0]/w)+'%';btn.style.top=(100*b[1]/h)+'%';
 btn.style.width=(100*(b[2]-b[0])/w)+'%';
 btn.style.height=(100*(b[3]-b[1])/h)+'%';
 btn.addEventListener('click',()=>selectRegion(r.region_id));
 canvas.append(btn);regions.set(r.region_id,r);buttons.set(r.region_id,btn);
}
for(const kind of [...new Set(report.regions.map(r=>r.region_kind))].sort()){
 visible.set(kind,true);
 const btn=add(document.getElementById('filters'),'button',kind+' ('+report.regions.filter(r=>r.region_kind===kind).length+')','toggle');
 btn.type='button';btn.setAttribute('aria-pressed','true');
 btn.addEventListener('click',()=>{
  const enabled=!visible.get(kind);visible.set(kind,enabled);btn.setAttribute('aria-pressed',String(enabled));
  for(const r of report.regions.filter(r=>r.region_kind===kind)){
   buttons.get(r.region_id).hidden=!enabled;
  }
 });
}
add(document.getElementById('summary'),'div',
  'Regionen: '+report.regions.length+' · Logische Elemente: '+report.logical_elements.length+
  ' · Beziehungen: '+report.relationships.length+' · Review: '+report.review_status,'summary');
add(document.getElementById('summary'),'small','PDF SHA-256: '+report.document_sha256);
function selectRegion(id){
 const r=regions.get(id);if(!r)return;
 for(const [key,button] of buttons)button.classList.toggle('selected',key===id);
 selection.replaceChildren();
 add(selection,'pre',JSON.stringify({
  id:r.region_id,typ:r.region_kind,seite:r.page_number,
  bbox_pt:r.bbox_pt,evidence:r.evidence,review:r.review
 },null,2));
 const related=report.relationships.filter(x=>x.from_id===id||x.to_id===id);
 if(related.length)add(selection,'pre','Verknüpfungen:\\n'+related.map(x=>x.relation_type+': '+x.from_id+' → '+x.to_id).join('\\n'));
}
for(const l of report.logical_elements){
 const block=add(document.getElementById('logical'),'div',undefined,'entry');
 add(block,'strong',l.label);add(block,'div','Status: '+l.review.status,'muted');
}
for(const r of report.regions.filter(x=>Object.prototype.hasOwnProperty.call(x,'raw_cells'))){
 const block=add(document.getElementById('matrices'),'div',undefined,'entry');
 const link=add(block,'button',r.region_id+' · Original-Zellmatrix');link.addEventListener('click',()=>selectRegion(r.region_id));
 const wrap=add(block,'div',undefined,'tablewrap'),table=add(wrap,'table');
 for(const row of r.raw_cells){
  const tr=add(table,'tr');
  for(const cell of row)add(tr,'td',cell===null?'[null]':cell);
 }
}
for(const r of report.relationships){
 const block=add(document.getElementById('relations'),'div',undefined,'entry');
 add(block,'strong',r.relation_type);
 add(block,'div',r.from_id+' → '+r.to_id);
 add(block,'small','Status: '+r.review.status+(r.review.reason?' · '+r.review.reason:''));
}
if(report.relationships.length===0)add(document.getElementById('relations'),'p','Keine Beziehungen','muted');
for(const d of report.review_decisions){
 const block=add(document.getElementById('decisions'),'div',undefined,'entry');
 add(block,'strong',d.status+' · '+d.target_id);
 add(block,'div',d.reviewer+' · '+d.decided_at);
 add(block,'small',d.reason);
}
if(report.review_decisions.length===0)add(document.getElementById('decisions'),'p','Noch keine Entscheidungen','muted');
</script>
</body></html>
"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-json",required=True,type=Path)
    parser.add_argument("--page",required=True,type=int)
    parser.add_argument("--image",required=True,type=Path,
                        help="Original unannotated PNG of the selected PDF page")
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args()
    if args.out.resolve() in {args.v02_json.resolve(),args.image.resolve()}:
        parser.error("Output must not overwrite input")
    data=json.loads(args.v02_json.read_text(encoding="utf-8"))
    rendered=make_html(data,page_number=args.page,
                       png_bytes=args.image.read_bytes(),image_name=args.image.name)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(rendered,encoding="utf-8")
    print("Lokale HTML-Review-Vorschau erstellt:",args.out)
    print("Nur Anzeige; keine Freigabe, keine Nextcloud-/DB-Schreibzugriffe")


if __name__=="__main__":
    main()
