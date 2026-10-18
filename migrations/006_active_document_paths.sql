BEGIN;

-- Eindeutigkeit des Dateipfads nur für aktive Dokumente.
-- Historische, deaktivierte Dokumente dürfen ihren alten Pfad behalten.

ALTER TABLE knowledge.document
    DROP CONSTRAINT document_nextcloud_path_key;

CREATE UNIQUE INDEX document_active_nextcloud_path_uidx
    ON knowledge.document (nextcloud_path)
    WHERE is_active = true;

COMMIT;
