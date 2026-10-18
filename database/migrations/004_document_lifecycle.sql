-- Retro-RAG Migration 004
-- Lebenszyklus von Wissensdokumenten
-- Migration ist wiederholt ausführbar.

ALTER TABLE knowledge.document
    ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN knowledge.document.is_active IS
    'true: Dokument fuer RAG freigegeben; false: Quelle verwaist oder deaktiviert';