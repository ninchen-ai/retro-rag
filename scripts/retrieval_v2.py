
#!/usr/bin/env python3
"""Retro-RAG v2: Read-only Vergleich zwischen pgvector und Hybrid-Retrieval."""

import argparse
import getpass
import os
import re

import psycopg
from scripts.ask_retro import ollama_post
from scripts.search_terms import expand_search_terms
from scripts.chunk_quality import classify_chunk, QUALITY_FACTORS

def get_embedding(question):
    result = ollama_post("/api/embed", {
        "model": "nomic-embed-text",
        "input": "search_query: " + question,
    })

    vectors = result.get("embeddings", [])
    if len(vectors) != 1 or len(vectors[0]) != 768:
        raise RuntimeError("Ungültiger Embedding-Vektor")

    return "[" + ",".join(map(str, vectors[0])) + "]"

def get_model_document_ids(cur, model_id):
    """Liefert Modell-Steckbrief, Handbücher und Chip-Datenblätter."""

    cur.execute("""
        SELECT d.id, d.document_key
        FROM knowledge.document d
        JOIN hw.component_model cm
          ON cm.document_id = d.id
        WHERE cm.id = %s
          AND d.is_active = true

        UNION

        SELECT d.id, d.document_key
        FROM knowledge.document d
        JOIN knowledge.document_component dc
          ON dc.document_id = d.id
        WHERE dc.component_model_id = %s
          AND dc.relation = 'manual'
          AND d.document_kind = 'manual'
          AND d.is_active = true

        UNION

        SELECT d.id, d.document_key
        FROM hw.component_chip cc
        JOIN knowledge.document_chip dc
          ON dc.chip_id = cc.chip_id
        JOIN knowledge.document d
          ON d.id = dc.document_id
        WHERE cc.component_model_id = %s
          AND dc.relation IN ('datasheet', 'reference', 'errata')
          AND d.document_kind = 'manual'
          AND d.is_active = true

        ORDER BY document_key
    """, (model_id, model_id, model_id))

    return cur.fetchall()

def vector_search(cur, vector, limit, document_ids=None):
    cur.execute("""
        SELECT
            c.id,
            d.document_key,
            c.chunk_index,
            c.page_start,
            1 - (c.embedding <=> %s::vector) AS score
        FROM rag.chunk c
        JOIN knowledge.document d ON d.id = c.document_id
        WHERE d.is_active = true
          AND c.embedding_model = 'nomic-embed-text'
          AND (%s::bigint[] IS NULL OR d.id = ANY(%s::bigint[]))
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s
    """, (vector, document_ids, document_ids, vector, limit))
    return cur.fetchall()


def text_search(cur, term, limit, document_ids=None):
    cur.execute("""
        WITH query AS (
            SELECT phraseto_tsquery('english', %s) AS q
        )
        SELECT
            c.id,
            d.document_key,
            c.chunk_index,
            c.page_start,
            ts_rank_cd(
                to_tsvector('english', c.content),
                query.q
            ) AS score
        FROM rag.chunk c
        JOIN knowledge.document d ON d.id = c.document_id
        CROSS JOIN query
        WHERE d.is_active = true
        AND (%s::bigint[] IS NULL OR d.id = ANY(%s::bigint[]))
          AND to_tsvector('english', c.content) @@ query.q
        ORDER BY score DESC, c.id
        LIMIT %s
    """, (term, document_ids, document_ids, limit))
    return cur.fetchall()


def reciprocal_rank_fusion(vector_rows, text_rows, k=60):
    results = {}

    for method, rows in (
        ("vector", vector_rows),
        ("text", text_rows),
    ):
        for rank, row in enumerate(rows, start=1):
            chunk_id = row[0]

            if chunk_id not in results:
                results[chunk_id] = {
                    "row": row,
                    "rrf": 0.0,
                    "ranks": {},
                }

            item = results[chunk_id]
            item["rrf"] += 1.0 / (k + rank)
            item["ranks"][method] = rank

    return sorted(
        results.values(),
        key=lambda item: (
            -item["rrf"],
            item["row"][0],
        ),
    )


def print_results(title, rows):
    print(f"\n===== {title} =====")

    for rank, row in enumerate(rows, start=1):
        _, doc, chunk, page, score = row
        print(
            f"{rank:2d}. {doc} "
            f"| Chunk {chunk} "
            f"| Seite {page} "
            f"| Score {score:.4f}"
        )

def detect_hardware_model(cur, question):
    """Erkennt bekannte Hardwaremodelle anhand des PostgreSQL-Katalogs."""

    cur.execute("""
        SELECT
            cm.id,
            mf.name,
            cm.model,
            cm.variant,
            d.document_key
        FROM hw.component_model cm
        JOIN hw.manufacturer mf
            ON mf.id = cm.manufacturer_id
        JOIN knowledge.document d
            ON d.id = cm.document_id
        WHERE d.is_active = true
        ORDER BY length(cm.model) DESC
    """)

    candidates = cur.fetchall()

    def normalized(value):
        return re.sub(r"[^a-z0-9]", "", value.casefold())

    normalized_question = normalized(question)

    matches = []

    for model_id, manufacturer, model, variant, document_key in candidates:
        normalized_model = normalized(model)

        if normalized_model in normalized_question:
            matches.append({
                "model_id": model_id,
                "manufacturer": manufacturer,
                "model": model,
                "variant": variant,
                "document_key": document_key,
            })

    return matches


def combine_text_results(search_lists):
    """Mehrere Volltext-Ranglisten zu einer Rangliste zusammenführen.

    Jeder Chunk erhält nur einen Rang anhand seiner besten Position.
    So zählt die Volltextsuche später nur als eine RRF-Quelle.
    """
    combined = {}

    for rows in search_lists:
        for rank, row in enumerate(rows, start=1):
            chunk_id = row[0]

            candidate = (rank, -float(row[4]), chunk_id, row)

            if (
                chunk_id not in combined
                or candidate[:3] < combined[chunk_id][:3]
            ):
                combined[chunk_id] = candidate

    ordered = sorted(
        combined.values(),
        key=lambda item: item[:3],
    )

    return [item[3] for item in ordered]


def get_primary_document(cur, model_id):
    """Lädt den führenden Markdown-Steckbrief eines Hardwaremodells."""

    cur.execute("""
        SELECT
            d.document_key,
            d.title,
            c.chunk_index,
            c.content
        FROM hw.component_model cm
        JOIN knowledge.document d
          ON d.id = cm.document_id
        JOIN rag.chunk c
          ON c.document_id = d.id
        WHERE cm.id = %s
          AND d.is_active = true
          AND d.document_kind = 'hardware_model'
          AND c.embedding_model = 'nomic-embed-text'
        ORDER BY c.chunk_index
    """, (model_id,))

    return cur.fetchall()

def apply_chunk_quality(cur, results):
    """Bewertet Treffer anhand der betroffenen PDF-Seiten."""

    if not results:
        return []

    chunk_ids = list({
        item["row"][0] for item in results
    })

    # Nur die tatsächlich gefundenen Chunks lesen.
    cur.execute("""
        SELECT
            c.id,
            c.document_id,
            c.page_start,
            c.content,
            d.document_kind
        FROM rag.chunk c
        JOIN knowledge.document d
          ON d.id = c.document_id
        WHERE c.id = ANY(%s::bigint[])
    """, (chunk_ids,))

    selected = {
        row[0]: row for row in cur.fetchall()
    }

    if len(selected) != len(chunk_ids):
        raise RuntimeError(
            "Nicht alle Retrieval-Chunks gefunden"
        )

    # Nur Seiten von tatsächlich gefundenen
    # PDF-Handbuch-Chunks untersuchen.
    pages = sorted({
        (document_id, page)
        for _, document_id, page, _, kind
        in selected.values()
        if kind == "manual" and page is not None
    })

    index_pages = set()

    if pages:
        doc_ids = [
            document_id for document_id, _
            in pages
        ]
        page_numbers = [
            page for _, page in pages
        ]

        cur.execute("""
            WITH target_pages AS (
                SELECT DISTINCT
                    document_id,
                    page_start
                FROM unnest(
                    %s::bigint[],
                    %s::integer[]
                ) AS p(document_id, page_start)
            )
            SELECT
                c.document_id,
                c.page_start,
                c.content
            FROM target_pages p
            JOIN rag.chunk c
              ON c.document_id = p.document_id
             AND c.page_start = p.page_start
        """, (doc_ids, page_numbers))

        for document_id, page, content in cur.fetchall():
            if classify_chunk(content) == "index":
                index_pages.add((document_id, page))

    ranked = []

    for item in results:
        chunk_id = item["row"][0]
        _, document_id, page, content, kind = selected[chunk_id]

        # Markdown und andere Dokumentarten unverändert lassen.
        if kind == "manual":
            quality = classify_chunk(content)

            if (
                quality == "content"
                and (document_id, page) in index_pages
            ):
                quality = "index"
        else:
            quality = "content"

        factor = QUALITY_FACTORS[quality]

        if factor == 0.0:
            continue

        ranked.append({
            **item,
            "quality": quality,
            "adjusted_rrf": item["rrf"] * factor,
        })

    return sorted(
        ranked,
        key=lambda item: (
            -item["adjusted_rrf"],
            item["row"][0],
        ),
    )

def hybrid_search(
    cur,
    question,
    term=None,
    candidates=20,
    top_k=5,
):
    """Hybrid-Retrieval mit modellbezogenen Hauptquellen."""

    if not 1 <= top_k <= candidates <= 100:
        raise ValueError("Ungültige Suchlimits")

    models = detect_hardware_model(cur, question)

    documents_by_id = {}
    primary_document = []

    # None = globale Suche.
    # [] = erkannte Hardware ohne zugeordnete PDFs.
    document_ids = None

    if models:
        for model in models:
            model_id = model["model_id"]

            # Markdown für JEDES erkannte Modell laden.
            primary = get_primary_document(
                cur, model_id
            )

            if not primary:
                raise RuntimeError(
                    "Markdown-Hauptquelle fehlt für "
                    f"{model['model']}"
                )

            primary_document.extend(primary)

            # Aktive Dokumentbeziehungen sammeln.
            for doc_id, doc_key in get_model_document_ids(
                cur, model_id
            ):
                documents_by_id[doc_id] = doc_key

        # Die Markdown-Hauptquellen nicht nochmals
        # als ergänzende Suchtreffer zurückgeben.
        primary_keys = {
            row[0] for row in primary_document
        }

        document_ids = [
            doc_id
            for doc_id, doc_key
            in documents_by_id.items()
            if doc_key not in primary_keys
        ]

    documents = sorted(
        documents_by_id.items(),
        key=lambda item: item[1],
    )

    # Suchbegriffe zusammenstellen.
    terms = []

    if term and term.strip():
        terms.append(term.strip())

    terms.extend(expand_search_terms(question))

    # Alle erkannten Modellnamen gehören in den
    # Dokumentfilter, nicht in die Volltextsuche.
    def normalize(value):
        return re.sub(
            r"[^a-z0-9]",
            "",
            value.casefold(),
        )

    hardware_names = set()

    for model in models:
        manufacturer = model["manufacturer"]
        model_name = model["model"]

        hardware_names.add(normalize(model_name))
        hardware_names.add(
            normalize(f"{manufacturer} {model_name}")
        )

    unique_terms = []
    seen = set()

    for search_term in terms:
        key = normalize(search_term)

        if not key or key in hardware_names:
            continue

        if key not in seen:
            seen.add(key)
            unique_terms.append(search_term)

    terms = unique_terms

    # Erkennt die Frage Hardware ohne PDF?
    # Dann reicht die garantierte Markdown-Hauptquelle.
    if document_ids == []:
        return {
            "models": models,
            "documents": documents,
            "primary_document": primary_document,
            "vectors": [],
            "texts": [],
            "results": [],
            "search_terms": terms,
        }

    vector = get_embedding(question)

    vectors = vector_search(
        cur,
        vector,
        candidates,
        document_ids,
    )

    text_lists = [
        text_search(
            cur,
            search_term,
            candidates,
            document_ids,
        )
        for search_term in terms
    ]

    texts = combine_text_results(text_lists)

    results = reciprocal_rank_fusion(
        vectors,
        texts,
    )

    results = apply_chunk_quality(
        cur,
        results,
    )

    return {
        "models": models,
        "documents": documents,
        "primary_document": primary_document,
        "vectors": vectors,
        "texts": texts,
        "results": results[:top_k],
        "search_terms": terms,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument(
        "--term",
        required=True,
        help="Exakter technischer Suchbegriff",
    )
    parser.add_argument("--candidates", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if not 1 <= args.top_k <= args.candidates <= 100:
        parser.error("Erforderlich: 1 <= top-k <= candidates <= 100")

    password = os.environ.get(
        "RETRO_RAG_READER_PASSWORD"
    ) or getpass.getpass("PostgreSQL-Lesepasswort: ")

    print("Erstelle Suchvektor ...")
    vector = get_embedding(args.question)

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
            models = detect_hardware_model(cur, args.question)

            document_ids = None

            if len(models) == 1:
                model = models[0]
                documents = get_model_document_ids(
                    cur, model["model_id"]
                )

                print("\n===== DOKUMENTFILTER =====")
                print(
                    f"Hardwaremodell: "
                    f"{model['manufacturer']} {model['model']}"
                )

                for document_id, document_key in documents:
                    print(f"  {document_key} (ID {document_id})")

                if not documents:
                    raise RuntimeError(
                        "Hardwaremodell erkannt, "
                        "aber keine aktiven Dokumente zugeordnet"
                    )

                document_ids = [
                    document_id
                    for document_id, _ in documents
                ]

            elif len(models) > 1:
                print(
                    "\nWARNUNG: Mehrere Hardwaremodelle erkannt. "
                    "Keine Modelleinschränkung."
                )

            vectors = vector_search(
                cur, vector, args.candidates, document_ids
            )
            texts = text_search(
                cur, args.term, args.candidates, document_ids
            )


    print("\n===== ERKANNTE HARDWAREMODELLE =====")

    if not models:
        print("Kein eindeutiges Hardwaremodell erkannt.")
    else:
        for model in models:
            print(
                f"{model['manufacturer']} {model['model']} "
                f"{model['variant']} "
                f"| ID {model['model_id']} "
                f"| {model['document_key']}"
            )


    print_results("VEKTORSUCHE", vectors)
    print_results("VOLLTEXTSUCHE", texts)

    merged = reciprocal_rank_fusion(vectors, texts)

    print("\n===== HYBRID RRF TOP 5 =====")

    for rank, item in enumerate(
        merged[:args.top_k], start=1
    ):
        _, doc, chunk, page, _ = item["row"]
        methods = ", ".join(
            f"{name}:#{position}"
            for name, position in item["ranks"].items()
        )

        print(
            f"{rank:2d}. {doc} "
            f"| Chunk {chunk} "
            f"| Seite {page} "
            f"| RRF {item['rrf']:.5f} "
            f"| {methods}"
        )


if __name__ == "__main__":
    main()
