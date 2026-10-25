#!/usr/bin/env python3
"""RCKS v0.3. Nextcloud is source of truth. --apply enables transactional writes."""
import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import sys
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

import psycopg
import yaml

DAV = {'d': 'DAV:', 'oc': 'http://owncloud.org/ns'}
CATEGORIES = {'grafikkarte','mainboard','cpu','ram','soundkarte','laufwerk','netzteil','controller','netzwerkkarte','erweiterungskarte','sonstiges'}
CONDITIONS = {'neu','gut','gebraucht','defekt','unbekannt'}
STATUSES = {'betriebsbereit','im_aufbau','eingelagert','defekt','unbekannt'}

EXCLUDED_DIRECTORIES = {
    "Import",
    "Vorlagen",
}

def check(condition, message):
    if not condition:
        raise ValueError(message)


def parse_md(data):
    text = data.decode('utf-8-sig')
    parts = re.split(r'^---\s*$', text, maxsplit=2, flags=re.M)
    check(len(parts) == 3 and not parts[0].strip(), 'YAML-Trennzeichen --- fehlen')
    meta = yaml.safe_load(parts[1])
    check(isinstance(meta, dict), 'Frontmatter muss ein YAML-Objekt sein')
    kind = meta.get('type')
    check(kind in ('hardware_model', 'inventory_item', 'system'), f'Nicht unterstützter Typ: {kind}')
    for key in ('id',):
        check(isinstance(meta.get(key), str) and meta[key].strip(), f'{key} fehlt')
    if kind == 'hardware_model':
        for key in ('model','manufacturer','category'):
            check(isinstance(meta.get(key), str) and meta[key].strip(), f'{key} fehlt')
        check(meta['category'] in CATEGORIES, 'Kategorie unbekannt')
        check(isinstance(meta.get('specs'),dict), 'specs muss ein Objekt sein')
        y = meta.get('year_released')
        check(y is None or (type(y) is int and 1940 <= y <= 2200), 'Ungültiges Erscheinungsjahr')
        if 'chips' in meta:
            chips = meta['chips']
            check(isinstance(chips, list), 'chips muss eine Liste sein')

            seen_chips = set()

            for chip in chips:
                check(isinstance(chip, dict), 'Ungültiger Chip-Eintrag')

                for field in ('manufacturer', 'name', 'role'):
                    value = chip.get(field)
                    check(
                        isinstance(value, str) and bool(value.strip()),
                        f'Chip: {field} fehlt'
                    )
                    check(
                        value == value.strip(),
                        f'Chip: {field} enthält Rand-Leerzeichen'
                    )

                identity = (
                    chip['manufacturer'].casefold(),
                    chip['name'].casefold(),
                    chip['role'].casefold(),
                )

                check(
                    identity not in seen_chips,
                    f'Doppelte Chip-Zuordnung: {identity}'
                )
                seen_chips.add(identity)
    elif kind == 'inventory_item':
        for key in ('asset_tag','component_model'):
            check(isinstance(meta.get(key),str) and meta[key].strip(), f'{key} fehlt')
        check(meta.get('condition','unbekannt') in CONDITIONS,'Ungültiger Zustand')
        check(isinstance(meta.get('instance_specs',{}),dict),'instance_specs muss ein Objekt sein')
    else:
        for key in ('slug','name'):
            check(isinstance(meta.get(key),str) and meta[key].strip(), f'{key} fehlt')
        check(meta.get('status','unbekannt') in STATUSES,'Ungültiger Systemstatus')
        comps = meta.get('components',[])
        check(isinstance(comps,list),'components muss eine Liste sein')
        for c in comps:
            check(isinstance(c,dict) and isinstance(c.get('asset_tag'),str),'Ungültige Systemkomponente')
    m = re.search(r'^#\s+(.+)$', parts[2], re.M)
    check(bool(m), 'Markdown-Hauptüberschrift fehlt')
    return meta, parts[2].strip(), m.group(1).strip()


class Cloud:
    def __init__(self, url, user, password, folder):
        s = urlsplit(url)
        check(s.scheme in ('http','https'), 'Ungültiges URL-Schema')
        check(s.scheme == 'https' or s.hostname in ('127.0.0.1','localhost','::1'), 'HTTP nur über localhost')
        self.base = url.rstrip('/')
        self.user = user
        self.prefix = f'/remote.php/dav/files/{quote(user,safe="")}/{quote(folder.strip("/"),safe="/")}/'
        self.headers = {'Authorization': 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()}

    def req(self, path, method='GET', depth=None):
        headers = self.headers.copy()
        if depth is not None:
            headers['Depth'] = str(depth)
        r = Request(self.base + path, method=method, headers=headers)
        with urlopen(r,timeout=30) as response:
            return response.read()

    def listing(self):
        queue = [self.prefix]
        seen = set()
        docs = []
        while queue:
            folder = queue.pop(0)
            if folder in seen:
                continue
            seen.add(folder)
            xml = ET.fromstring(self.req(folder,'PROPFIND',1))
            for response in xml.findall('d:response',DAV):
                href = response.findtext('d:href', namespaces=DAV)
                if not href:
                    continue
                path = urlsplit(href).path
                clean = unquote(path)
                base_clean = unquote(self.prefix)
                if clean.rstrip('/') == base_clean.rstrip('/'):
                    continue
                check(clean.startswith(base_clean),'WebDAV lieferte Pfad außerhalb des Projekts')
                directory = response.find('.//d:resourcetype/d:collection',DAV) is not None
                if directory:
                    queue.append(path if path.endswith('/') else path+'/')
                elif clean.lower().endswith('.md'):
                    raw = self.req(path)
                    # Explicit request for stable Nextcloud ID; fail closed when absent.
                    propbody = b'<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns"><d:prop><oc:fileid/></d:prop></d:propfind>'
                    request = Request(self.base + path,data=propbody, method='PROPFIND',headers={**self.headers,'Depth':'0','Content-Type':'application/xml'})
                    with urlopen(request, timeout=30) as res:
                        fxml = ET.fromstring(res.read())
                    fid = fxml.findtext('.//oc:fileid',namespaces=DAV)
                    check(fid and fid.strip(),f'Nextcloud fileid fehlt für {clean}')
                    try:
                        meta, body, title = parse_md(raw)
                    except (ValueError, UnicodeDecodeError, Exception) as exc:
                        raise ValueError(
                            f"Markdown-Validierungsfehler in Nextcloud-Datei: {clean} "
                            f"(File-ID: {fid.strip()}): {exc}"
                        ) from exc
                    docs.append({'path':clean,'fileid':fid.strip(),'raw':raw,'meta':meta,'body':body,'title':title})
        return docs


def validate_relations(docs):
    keys, tags, slugs = set(),set(),set()
    models = set()
    for d in docs:
        m = d['meta']
        check(m['id'] not in keys,f'Doppelte Dokument-ID {m["id"]}')
        keys.add(m['id'])
        if m['type']=='hardware_model':models.add(m['id'])
        if m['type']=='inventory_item':
            tag=m['asset_tag']
            check(tag not in tags,f'Doppelte Inventar-ID {tag}')
            tags.add(tag)
        if m['type']=='system':
            check(m['slug'] not in slugs,f'Doppelter System-Slug {m["slug"]}')
            slugs.add(m['slug'])
    for d in docs:
        m=d['meta']
        if m['type']=='inventory_item':
            check(m['component_model'] in models,f'Modell {m["component_model"]} nicht in Nextcloud')
        if m['type']=='system':
            for comp in m.get('components',[]):
                check(comp['asset_tag'] in tags,f'Inventar {comp["asset_tag"]} nicht in Nextcloud')


def find_unchanged(cur, docs):
    # Skip unchanged content; resolve existing IDs for relations.
    unchanged = set()
    rows = {}
    for d in docs:
        m = d['meta']
        sha = hashlib.sha256(d['raw']).hexdigest()
        cur.execute('''SELECT id, content_sha256, nextcloud_file_id, nextcloud_path, document_kind
                       FROM knowledge.document WHERE document_key=%s AND origin='own' ''', (m['id'],))
        row = cur.fetchone()
        if row and row[1] == sha and row[2] == d['fileid'] and row[3] == d['path'] and row[4] == m['type']:
            unchanged.add(m['id'])
            rows[m['id']] = row[0]
    return unchanged, rows


def upsert_document(cur,d):
    m=d['meta']
    relative=d['path']
    digest=hashlib.sha256(d['raw']).hexdigest()
    cur.execute('''INSERT INTO knowledge.document
        (document_key,document_kind,origin,nextcloud_file_id,nextcloud_path,content_sha256,title,indexed_at)
        VALUES (%s,%s,'own',%s,%s,%s,%s,now())
        ON CONFLICT(document_key) DO UPDATE SET
          document_kind=excluded.document_kind,nextcloud_file_id=excluded.nextcloud_file_id,
          nextcloud_path=excluded.nextcloud_path,content_sha256=excluded.content_sha256,
          title=excluded.title,indexed_at=now()
        WHERE knowledge.document.origin='own'
        RETURNING id''', (m['id'],m['type'],d['fileid'],relative,digest,d['title']))
    result=cur.fetchone()
    check(result is not None,f'Dokument {m["id"]} darf nicht aktualisiert werden')
    return result[0]


def upsert_model(cur,d,document_id):
    m=d['meta']
    cur.execute('INSERT INTO hw.manufacturer(name) VALUES (%s) ON CONFLICT(name) DO UPDATE SET name=excluded.name RETURNING id',(m['manufacturer'],))
    manufacturer_id=cur.fetchone()[0]
    cur.execute('SELECT id FROM hw.category WHERE slug=%s',(m['category'],))
    category=cur.fetchone()
    check(category is not None,'Kategorie nicht in hw.category')
    cur.execute('''INSERT INTO hw.component_model(document_id,category_id,manufacturer_id,model,variant,year_released,specs,notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT(document_id) DO UPDATE SET category_id=excluded.category_id,
          manufacturer_id=excluded.manufacturer_id,model=excluded.model,
          variant=excluded.variant,year_released=excluded.year_released,
          specs=excluded.specs,notes=excluded.notes RETURNING id''',
        (document_id,category[0],manufacturer_id,m['model'],m.get('variant'),m.get('year_released'),json.dumps(m['specs']),d['body']))
    return cur.fetchone()[0]

def upsert_chip(cur, manufacturer, name):
    """Legt einen Chip an oder ermittelt seine vorhandene ID."""

    cur.execute("""
        INSERT INTO hw.manufacturer (name)
        VALUES (%s)
        ON CONFLICT (name)
        DO UPDATE SET name = EXCLUDED.name
        RETURNING id
    """, (manufacturer,))

    manufacturer_id = cur.fetchone()[0]

    cur.execute("""
        INSERT INTO hw.chip (manufacturer_id, name)
        VALUES (%s, %s)
        ON CONFLICT (manufacturer_id, name)
        DO UPDATE SET name = EXCLUDED.name
        RETURNING id
    """, (manufacturer_id, name))

    return cur.fetchone()[0]


def sync_model_chips(cur, model_id, chips):
    """Synchronisiert die Chipbeziehungen eines Hardwaremodells."""

    for chip in chips:
        chip_id = upsert_chip(
            cur,
            chip["manufacturer"],
            chip["name"],
        )

        cur.execute("""
            INSERT INTO hw.component_chip (
                component_model_id,
                chip_id,
                role
            )
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            model_id,
            chip_id,
            chip["role"],
        ))

def upsert_item(cur,d,docid,modelids):
    m=d['meta']
    cur.execute('''INSERT INTO hw.inventory_item
      (asset_tag,document_id,component_model_id,serial_number,condition,location,instance_specs,notes)
      VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
      ON CONFLICT(document_id) DO UPDATE SET
       asset_tag=excluded.asset_tag,component_model_id=excluded.component_model_id,
       serial_number=excluded.serial_number,condition=excluded.condition,
       location=excluded.location,instance_specs=excluded.instance_specs,
       notes=excluded.notes RETURNING id''',
      (m['asset_tag'],docid,modelids[m['component_model']],m.get('serial_number'),m.get('condition','unbekannt'),m.get('location'),json.dumps(m.get('instance_specs',{})),d['body']))
    return cur.fetchone()[0]


def upsert_system(cur,d,docid):
    m=d['meta']
    cur.execute('''INSERT INTO hw.system (slug,document_id,name,status,description,location)
      VALUES (%s,%s,%s,%s,%s,%s)
      ON CONFLICT(document_id) DO UPDATE SET slug=excluded.slug,name=excluded.name,
       status=excluded.status,description=excluded.description,location=excluded.location RETURNING id''',
      (m['slug'],docid,m['name'],m.get('status','unbekannt'),d['body'],m.get('location')))
    system_id=cur.fetchone()[0]
    # Initially append/update active assignments only. Never silently erase history.
    for comp in m.get('components',[]):
        cur.execute('SELECT id FROM hw.inventory_item WHERE asset_tag=%s',(comp['asset_tag'],))
        item=cur.fetchone()
        check(item is not None,f'Inventarobjekt {comp["asset_tag"]} fehlt')
        cur.execute('SELECT id,system_id FROM hw.system_component WHERE inventory_item_id=%s AND removed_at IS NULL',(item[0],))
        active=cur.fetchone()
        label=comp.get('slot_label') or comp.get('role')
        if active:
            check(active[1]==system_id,f'{comp["asset_tag"]} ist bereits in einem anderen System verbaut')
            cur.execute('UPDATE hw.system_component SET slot_label=%s WHERE id=%s',(label,active[0]))
        else:
            cur.execute('INSERT INTO hw.system_component(system_id,inventory_item_id,slot_label) VALUES (%s,%s,%s)',(system_id,item[0],label))
    return system_id


def main():
    p=argparse.ArgumentParser(description='Nextcloud -> PostgreSQL Retro-RAG v0.3 (standardmäßig read-only)')
    p.add_argument('--url',default='http://127.0.0.1:8080')
    p.add_argument('--user',default='nina')
    p.add_argument('--folder',default='Retro-Computing')
    p.add_argument('--apply',action='store_true',help='Transaktion tatsächlich committen')
    args=p.parse_args()
    cloud=Cloud(args.url,args.user,os.environ.get('NEXTCLOUD_APP_PASSWORD') or getpass.getpass('Nextcloud-App-Passwort: '),args.folder)
    docs=cloud.listing()
    check(bool(docs),'Keine Markdown-Dateien gefunden')
    validate_relations(docs)
    for d in sorted(docs,key=lambda x:('hardware_model','inventory_item','system').index(x['meta']['type'])):
        print(f'OK {d["meta"]["type"]:14} {d["meta"]["id"]:30} {d["path"]}')
    print(f'Validierung erfolgreich: {len(docs)} Dokumente')
    if not args.apply:
        print('DRY-RUN: PostgreSQL wurde nicht kontaktiert oder verändert. --apply aktiviert den Import.')
        return 0
    print('Importmodus: PostgreSQL-Transaktion')
    with psycopg.connect(host='127.0.0.1',port=5432,dbname='retro_rag',user='retro_rag_ingest',password=os.environ.get('PGPASSWORD') or getpass.getpass('Passwort für retro_rag_ingest: '),connect_timeout=10) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute('SELECT current_user, current_database()')
                role,dbname=cur.fetchone()
                check(role=='retro_rag_ingest' and dbname=='retro_rag','Falsche Datenbank/Rolle')
                unchanged, docids = find_unchanged(cur, docs)
                for d in docs:
                    if d['meta']['id'] not in unchanged:
                        docids[d['meta']['id']] = upsert_document(cur,d)
                models = {}
                for d in docs:
                    if d['meta']['type'] != 'hardware_model':
                        continue
                    key = d['meta']['id']
                    if key in unchanged:
                        cur.execute('SELECT id FROM hw.component_model WHERE document_id=%s', (docids[key],))
                        row = cur.fetchone()
                        if row:
                            models[key] = row[0]
                            continue
                    models[key] = upsert_model(cur,d,docids[key])

                # Chipbeziehungen aller Hardwaremodelle synchronisieren.
                # Auch unveränderte Modelle werden berücksichtigt.
                for d in docs:
                    if d['meta']['type'] != 'hardware_model':
                        continue

                    chips = d['meta'].get('chips', [])
                    if not chips:
                        continue

                    key = d['meta']['id']

                    sync_model_chips(
                        cur,
                        models[key],
                        chips,
                    )

                # Inventarobjekte importieren
                for d in docs:
                    if d['meta']['type']=='inventory_item':
                        key = d['meta']['id']
                        if key in unchanged:
                            cur.execute('SELECT id FROM hw.inventory_item WHERE document_id=%s', (docids[key],))
                            if cur.fetchone():
                                continue
                        upsert_item(cur,d,docids[key],models)

                # Systeme importieren
                for d in docs:
                    if d['meta']['type']=='system':
                        key = d['meta']['id']
                        if key in unchanged:
                            cur.execute('SELECT id FROM hw.system WHERE document_id=%s', (docids[key],))
                            if cur.fetchone():
                                continue
                        upsert_system(cur,d,docids[key])

                print(f'Geändert/neu: {len(docs)-len(unchanged)} | Übersprungen: {len(unchanged)}')
    print('COMMIT: Dokumente, Modelle, Inventar und Systeme synchronisiert.')
    print('Hinweis: Entfernte Dokumente/Komponenten werden v0.2 bewusst NICHT automatisch gelöscht.')
    return 0

if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'FEHLER: {exc}',file=sys.stderr)
        sys.exit(1)
