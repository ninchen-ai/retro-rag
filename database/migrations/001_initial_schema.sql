-- Retro Computing Knowledge System (RCKS)
-- PostgreSQL 16 + pgvector | Migration 001 | 2026-10-13
-- Run ONLY within the dedicated database retro_rag, never in codeanalyse/nextcloud.
-- Nextcloud Markdown is authoritative; PostgreSQL is a synchronized projection and search index.
-- External research candidates are NOT stored here before user approval.
BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS knowledge;
CREATE SCHEMA IF NOT EXISTS hw;
CREATE SCHEMA IF NOT EXISTS rag;

-- Common updated_at trigger, explicitly schema-qualified for safety.
CREATE OR REPLACE FUNCTION public.rcks_touch_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- 1. Provenance and documents -----------------------------------------------
-- Entries here represent sources ALREADY approved for permanent import.
-- Unapproved external results stay in an ephemeral application review queue.
CREATE TABLE knowledge.source (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_key          text NOT NULL UNIQUE,
    title               text NOT NULL,
    url                 text NOT NULL,
    publisher           text,
    source_type         text NOT NULL CHECK (source_type IN ('vendor', 'official', 'archive', 'community', 'other')),
    license_note        text,
    verified_at         timestamptz,
    approved_at         timestamptz NOT NULL,
    approved_by         text NOT NULL CHECK (length(btrim(approved_by)) > 0),
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT source_http_url_chk CHECK (url ~* '^https?://[^[:space:]]+$')
);

CREATE TABLE knowledge.document (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_key        text NOT NULL UNIQUE,  -- YAML frontmatter id
    document_kind       text NOT NULL CHECK (document_kind IN
                          ('hardware_model','inventory_item','system','reference','manual','other')),
    origin              text NOT NULL DEFAULT 'own' CHECK (origin IN ('own','approved_external')),
    source_id           bigint REFERENCES knowledge.source(id) ON DELETE RESTRICT,
    nextcloud_file_id   text NOT NULL UNIQUE,
    nextcloud_path      text NOT NULL UNIQUE, -- Relative WebDAV path; never local container path
    content_sha256      text NOT NULL CHECK (content_sha256 ~ '^[a-fA-F0-9]{64}$'),
    title               text NOT NULL,
    language_code       text,
    revision            integer NOT NULL DEFAULT 1 CHECK (revision > 0),
    indexed_at          timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_external_requires_source_chk
      CHECK (origin <> 'approved_external' OR source_id IS NOT NULL),
    CONSTRAINT document_markdown_chk CHECK (nextcloud_path ~* '\.md$')
);
CREATE INDEX document_source_idx ON knowledge.document(source_id);
CREATE INDEX document_kind_idx ON knowledge.document(document_kind);
CREATE TRIGGER document_touch BEFORE UPDATE ON knowledge.document
FOR EACH ROW EXECUTE FUNCTION public.rcks_touch_updated_at();

-- Verify an externally imported document points to an approved source (which
-- is the only kind permitted in knowledge.source). Application still enforces
-- authenticated human approval before writing the Nextcloud Markdown.

CREATE TABLE knowledge.topic (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug                text NOT NULL UNIQUE,
    name                text NOT NULL,
    description         text
);
CREATE TABLE knowledge.document_topic (
    document_id         bigint NOT NULL REFERENCES knowledge.document(id) ON DELETE CASCADE,
    topic_id            bigint NOT NULL REFERENCES knowledge.topic(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, topic_id)
);

-- 2. Hardware catalog and physical inventory --------------------------------
CREATE TABLE hw.manufacturer (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                text NOT NULL UNIQUE
);
CREATE TABLE hw.category (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug                text NOT NULL UNIQUE,
    name                text NOT NULL
);
CREATE TABLE hw.chip (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manufacturer_id     integer NOT NULL REFERENCES hw.manufacturer(id),
    name                text NOT NULL,
    architecture        text,
    process_nm          numeric(8,2) CHECK (process_nm > 0),
    year_released       smallint CHECK (year_released BETWEEN 1940 AND 2200),
    notes               text,
    UNIQUE (manufacturer_id, name)
);
CREATE TABLE hw.interface (
    id                  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                text NOT NULL UNIQUE,
    interface_kind      text NOT NULL DEFAULT 'other' CHECK (interface_kind IN
                          ('bus','slot','socket','memory','connector','other'))
);
CREATE TABLE hw.component_model (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id         bigint NOT NULL UNIQUE REFERENCES knowledge.document(id) ON DELETE RESTRICT,
    category_id         integer NOT NULL REFERENCES hw.category(id),
    manufacturer_id     integer NOT NULL REFERENCES hw.manufacturer(id),
    model               text NOT NULL,
    variant             text,
    year_released       smallint CHECK (year_released BETWEEN 1940 AND 2200),
    specs               jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(specs) = 'object'),
    notes               text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT component_model_unique UNIQUE NULLS NOT DISTINCT (manufacturer_id, model, variant)
);
CREATE INDEX component_model_category_idx ON hw.component_model(category_id);
CREATE INDEX component_model_specs_gin ON hw.component_model USING gin(specs);
CREATE TRIGGER component_model_touch BEFORE UPDATE ON hw.component_model
FOR EACH ROW EXECUTE FUNCTION public.rcks_touch_updated_at();

-- Multiple chips per board: GPU, northbridge, southbridge, audio, etc.
CREATE TABLE hw.component_chip (
    component_model_id  bigint NOT NULL REFERENCES hw.component_model(id) ON DELETE CASCADE,
    chip_id             integer NOT NULL REFERENCES hw.chip(id),
    role                text NOT NULL,
    PRIMARY KEY (component_model_id, chip_id, role)
);
CREATE INDEX component_chip_chip_idx ON hw.component_chip(chip_id);

CREATE TABLE hw.component_interface (
    component_model_id  bigint NOT NULL REFERENCES hw.component_model(id) ON DELETE CASCADE,
    interface_id        integer NOT NULL REFERENCES hw.interface(id),
    role                text NOT NULL CHECK (role IN ('uses','provides')),
    quantity            smallint NOT NULL DEFAULT 1 CHECK (quantity > 0),
    notes               text,
    PRIMARY KEY (component_model_id, interface_id, role)
);
CREATE INDEX component_interface_interface_idx ON hw.component_interface(interface_id);

-- The real-world individual unit; overrides are instance-specific facts,
-- e.g. modified BIOS, installed memory, overclock, measured values.
CREATE TABLE hw.inventory_item (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_tag           text NOT NULL UNIQUE, -- Stable ID in Nextcloud YAML
    document_id         bigint NOT NULL UNIQUE REFERENCES knowledge.document(id) ON DELETE RESTRICT,
    component_model_id  bigint NOT NULL REFERENCES hw.component_model(id),
    serial_number       text,
    condition           text NOT NULL DEFAULT 'unbekannt' CHECK (condition IN
                          ('neu','gut','gebraucht','defekt','unbekannt')),
    location            text,
    instance_specs      jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(instance_specs) = 'object'),
    acquired_at         date,
    notes               text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX inventory_item_model_idx ON hw.inventory_item(component_model_id);
CREATE INDEX inventory_item_specs_gin ON hw.inventory_item USING gin(instance_specs);
CREATE TRIGGER inventory_item_touch BEFORE UPDATE ON hw.inventory_item
FOR EACH ROW EXECUTE FUNCTION public.rcks_touch_updated_at();

-- A complete retro computer/system is distinct from an individual component.
CREATE TABLE hw.system (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug                text NOT NULL UNIQUE,
    document_id         bigint NOT NULL UNIQUE REFERENCES knowledge.document(id) ON DELETE RESTRICT,
    name                text NOT NULL,
    description         text,
    status              text NOT NULL DEFAULT 'unbekannt' CHECK (status IN
                          ('betriebsbereit','im_aufbau','eingelagert','defekt','unbekannt')),
    location            text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER system_touch BEFORE UPDATE ON hw.system
FOR EACH ROW EXECUTE FUNCTION public.rcks_touch_updated_at();

-- Keep installation history and prevent one physical part being installed
-- in two systems at the same time.
CREATE TABLE hw.system_component (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_id           bigint NOT NULL REFERENCES hw.system(id) ON DELETE CASCADE,
    inventory_item_id   bigint NOT NULL REFERENCES hw.inventory_item(id) ON DELETE RESTRICT,
    slot_label          text,
    installed_at        date,
    removed_at          date,
    notes               text,
    CHECK (removed_at IS NULL OR installed_at IS NULL OR removed_at >= installed_at)
);
CREATE UNIQUE INDEX system_component_one_active_system_idx
    ON hw.system_component(inventory_item_id) WHERE removed_at IS NULL;
CREATE INDEX system_component_system_idx ON hw.system_component(system_id);

-- Photos/manuals are stored in Nextcloud; DB stores only references + metadata.
-- Every media object belongs to exactly one model, inventory item or system.
CREATE TABLE hw.media (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    component_model_id  bigint REFERENCES hw.component_model(id) ON DELETE CASCADE,
    inventory_item_id   bigint REFERENCES hw.inventory_item(id) ON DELETE CASCADE,
    system_id           bigint REFERENCES hw.system(id) ON DELETE CASCADE,
    kind                text NOT NULL DEFAULT 'foto' CHECK (kind IN
                          ('foto','scan','diagramm','datenblatt','sonstiges')),
    nextcloud_file_id   text NOT NULL UNIQUE,
    nextcloud_path      text NOT NULL,
    sha256              text CHECK (sha256 IS NULL OR sha256 ~ '^[a-fA-F0-9]{64}$'),
    mime_type           text,
    width_px            integer CHECK (width_px > 0),
    height_px           integer CHECK (height_px > 0),
    caption             text,
    taken_at            timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT media_exactly_one_owner_chk
      CHECK (num_nonnulls(component_model_id, inventory_item_id, system_id) = 1)
);
CREATE INDEX media_item_idx ON hw.media(inventory_item_id);
CREATE INDEX media_model_idx ON hw.media(component_model_id);
CREATE INDEX media_system_idx ON hw.media(system_id);
CREATE INDEX media_sha256_idx ON hw.media(sha256);

-- Connections between searchable reference documents and related hardware.
CREATE TABLE knowledge.document_component (
    document_id         bigint NOT NULL REFERENCES knowledge.document(id) ON DELETE CASCADE,
    component_model_id  bigint NOT NULL REFERENCES hw.component_model(id) ON DELETE CASCADE,
    relation            text NOT NULL DEFAULT 'describes' CHECK (relation IN
                          ('describes','mentions','driver','manual','compatibility')),
    PRIMARY KEY (document_id, component_model_id, relation)
);
CREATE INDEX document_component_model_idx ON knowledge.document_component(component_model_id);

-- 3. Search index and ingestion jobs -----------------------------------------
-- v1 uses a SINGLE embedding family/dimension, deliberately fixed to avoid
-- cosine comparisons across incompatible embedding models.
CREATE TABLE rag.chunk (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id         bigint NOT NULL REFERENCES knowledge.document(id) ON DELETE CASCADE,
    chunk_index         integer NOT NULL CHECK (chunk_index >= 0),
    heading             text,
    content             text NOT NULL CHECK (length(btrim(content)) > 0),
    token_count         integer CHECK (token_count > 0),
    embedding_model     text NOT NULL DEFAULT 'nomic-embed-text' CHECK (embedding_model = 'nomic-embed-text'),
    embedding           vector(768) NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index, embedding_model)
);
CREATE INDEX rag_chunk_document_idx ON rag.chunk(document_id);
CREATE INDEX rag_chunk_hnsw_idx ON rag.chunk USING hnsw (embedding vector_cosine_ops);
CREATE INDEX rag_chunk_fts_idx ON rag.chunk USING gin (to_tsvector('simple', content));

CREATE TABLE rag.ingestion_job (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_key        text NOT NULL,
    document_id         bigint REFERENCES knowledge.document(id) ON DELETE SET NULL,
    action              text NOT NULL CHECK (action IN ('create','update','delete','reindex')),
    status              text NOT NULL CHECK (status IN ('queued','running','completed','failed')),
    error_message       text,
    started_at          timestamptz,
    completed_at        timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ingestion_job_status_idx ON rag.ingestion_job(status, created_at);

INSERT INTO hw.category(slug, name) VALUES
 ('grafikkarte','Grafikkarte'), ('mainboard','Mainboard'),
 ('cpu','Prozessor'), ('ram','Arbeitsspeicher'),
 ('soundkarte','Soundkarte'), ('laufwerk','Laufwerk / Datenträger'),
 ('netzteil','Netzteil'), ('controller','Controllerkarte'),
 ('netzwerkkarte','Netzwerkkarte'), ('erweiterungskarte','Erweiterungskarte'),
 ('sonstiges','Sonstiges')
ON CONFLICT (slug) DO NOTHING;

COMMIT;
