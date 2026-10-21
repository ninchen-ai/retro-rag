#!/usr/bin/env python3
"""Adapter zwischen Retro-RAG Retrieval v2 und der Chat-API."""

import psycopg

from scripts.retrieval_v2 import hybrid_search
from scripts.hardware_facts import (
    extract_hardware_facts,
    format_hardware_facts,
)


def retrieve_context_v2(
    question,
    password,
    candidates=20,
    top_k=5,
):
    """Liefert formatierten Kontext und tatsächlich geladene Quellen."""

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="retro_rag",
        user="retro_rag_reader",
        password=password,
        connect_timeout=10,
        options="-c default_transaction_read_only=on",
    ) as conn:
        with conn.cursor() as cur:

            # Bestehende strukturierte Inventarabfrage
            # aus Retrieval v1 beibehalten.
            cur.execute("""
                SELECT
                    s.name,
                    sc.slot_label,
                    i.asset_tag,
                    mf.name,
                    m.model,
                    COALESCE(m.variant, '')
                FROM hw.system AS s
                JOIN hw.system_component AS sc
                  ON sc.system_id = s.id
                JOIN hw.inventory_item AS i
                  ON i.id = sc.inventory_item_id
                JOIN hw.component_model AS m
                  ON m.id = i.component_model_id
                JOIN hw.manufacturer AS mf
                  ON mf.id = m.manufacturer_id
                WHERE sc.removed_at IS NULL
                ORDER BY s.name, sc.slot_label, i.asset_tag
                LIMIT 100
            """)

            inventory = cur.fetchall()

            retrieval = hybrid_search(
                cur,
                question=question,
                term=None,
                candidates=candidates,
                top_k=top_k,
            )

            passages = []
            seen = set()

            # Führende Markdown-Steckbriefe zuerst.
            for key, title, chunk_index, content in (
                retrieval["primary_document"]
            ):
                identity = (key, chunk_index)

                if identity in seen:
                    continue

                seen.add(identity)

                passages.append({
                    "key": key,
                    "title": title,
                    "chunk": chunk_index,
                    "content": content,
                    "page_start": None,
                    "page_end": None,
                    "role": "primary",
                })

            # Nur die ausgewählten Suchtreffer nachladen.
            results = retrieval["results"]
            chunk_ids = [
                item["row"][0]
                for item in results
            ]

            chunks = {}

            if chunk_ids:
                cur.execute("""
                    SELECT
                        c.id,
                        d.document_key,
                        d.title,
                        c.chunk_index,
                        c.content,
                        c.page_start,
                        c.page_end,
                        d.document_kind
                    FROM rag.chunk c
                    JOIN knowledge.document d
                      ON d.id = c.document_id
                    WHERE c.id = ANY(%s::bigint[])
                      AND d.is_active = true
                """, (chunk_ids,))

                chunks = {
                    row[0]: row
                    for row in cur.fetchall()
                }

                if len(chunks) != len(set(chunk_ids)):
                    raise RuntimeError(
                        "Nicht alle Suchtreffer lesbar"
                    )

            for item in results:
                chunk_id = item["row"][0]

                (
                    _,
                    key,
                    title,
                    chunk_index,
                    content,
                    page_start,
                    page_end,
                    document_kind,
                ) = chunks[chunk_id]

                identity = (key, chunk_index)

                if identity in seen:
                    continue

                seen.add(identity)

                passages.append({
                    "key": key,
                    "title": title,
                    "chunk": chunk_index,
                    "content": content,
                    "page_start": page_start,
                    "page_end": page_end,
                    "role": (
                        "manual"
                        if document_kind == "manual"
                        else "retrieved"
                    ),
                    "quality": item.get(
                        "quality", "content"
                    ),
                })

    context = format_context_v2(inventory, passages)

    return {
        "context": context,
        "inventory": inventory,
        "passages": passages,
        "models": retrieval["models"],
        "search_terms": retrieval["search_terms"],
    }


def format_context_v2(inventory, passages):
    """Erstellt den Antwortkontext ohne irreführende Score-Angaben."""

    lines = [
        "STRUKTURIERTE INVENTARDATEN "
        "(aktuell verbaute Komponenten):"
    ]

    if inventory:
        for (
            system,
            role,
            asset,
            manufacturer,
            model,
            variant,
        ) in inventory:
            lines.append(
                f"- System: {system}; "
                f"Funktion: {role}; "
                f"Inventar: {asset}; "
                f"Hersteller/Modell: "
                f"{manufacturer} {model} {variant}"
            )
    else:
        lines.append(
            "- Keine aktiven Systemkomponenten dokumentiert."
        )

    primary = [
        p for p in passages
        if p["role"] == "primary"
    ]

    hardware_facts = extract_hardware_facts(primary)

    if hardware_facts:
        lines.append(
            "\n" + format_hardware_facts(hardware_facts)
        )

        lines.append(
            "\nDie strukturierten Hardwaredaten sind "
            "jeweils ausschließlich dem angegebenen "
            "Modell zugeordnet. Werte verschiedener "
            "Modelle dürfen nicht vermischt werden. "
            "Nicht angegebene Eigenschaften sind "
            "unbekannt und dürfen nicht ergänzt werden."
        )
    lines.append("\nFÜHRENDE MARKDOWN-STECKBRIEFE:")

    for p in primary:
        lines.append(
            f"\n[Markdown-Hauptquelle: {p['key']} "
            f"| Titel: {p['title']}]"
        )
        lines.append(p["content"][:6000])

    if not primary:
        lines.append(
            "Keine separat ermittelte Markdown-Hauptquelle."
        )

    lines.append("\nERGÄNZENDE SUCHERGEBNISSE:")

    supplementary = [
        p for p in passages
        if p["role"] != "primary"
    ]

    for p in supplementary:
        page_info = ""

        if p["page_start"] is not None:
            page_info = (
                f" | PDF-Seite {p['page_start']}"
            )

        lines.append(
            f"\n[Quelle: {p['key']} "
            f"| Abschnitt {p['chunk']} "
            f"| Titel: {p['title']}"
            f"{page_info}]"
        )
        lines.append(p["content"][:6000])

    if not supplementary:
        lines.append(
            "Keine ergänzenden Suchergebnisse."
        )

    return "\n".join(lines)
