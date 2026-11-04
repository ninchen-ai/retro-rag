"""Static migration guardrails. PostgreSQL integration tests are still required."""
from pathlib import Path
import unittest

SQL = (
    Path(__file__).resolve().parents[1]
    / "database/migrations/005_multi_model_embeddings.sql"
).read_text(encoding="utf-8")


class MigrationSafetyTests(unittest.TestCase):
    def test_additive_only(self):
        self.assertNotIn("DROP TABLE", SQL.upper())
        self.assertNotIn("ALTER TABLE RAG.CHUNK", SQL.upper())
        self.assertIn("ON DELETE CASCADE", SQL.upper())

    def test_model_specific_dimensions(self):
        self.assertIn("vector_dims(embedding) = 768", SQL)
        self.assertIn("vector_dims(embedding) = 1024", SQL)
        self.assertIn("embedding::vector(768)", SQL)
        self.assertIn("embedding::vector(1024)", SQL)

    def test_existing_vectors_backfilled(self):
        self.assertIn("FROM rag.chunk", SQL)
        self.assertIn("ON CONFLICT (chunk_id, embedding_model) DO NOTHING", SQL)


if __name__ == "__main__":
    unittest.main()
