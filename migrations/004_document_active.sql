-- Aktivstatus für Dokumente
ALTER TABLE knowledge.document
    ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true;
