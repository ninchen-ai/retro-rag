import unittest

from llm_import.variant_evidence import extract_variant_memory


class TestVariantEvidence(unittest.TestCase):

    def test_two_model_capacities(self):
        source = (
            "Integrated with 128MB(GV-R92S128T)/"
            "64MB(GV-R92S64T) DDR memory"
        )

        result = extract_variant_memory(
            source,
            ["GV-R92S128T", "GV-R92S64T"],
        )

        self.assertEqual(result["GV-R92S128T"], 128)
        self.assertEqual(result["GV-R92S64T"], 64)

    def test_missing_capacity(self):
        result = extract_variant_memory(
            "GV-R92S128T supports DDR memory",
            ["GV-R92S128T"],
        )

        self.assertIsNone(result["GV-R92S128T"])

    def test_conflicting_capacities(self):
        source = (
            "128MB(GV-R92S128T) "
            "256MB(GV-R92S128T)"
        )

        result = extract_variant_memory(
            source,
            ["GV-R92S128T"],
        )

        self.assertIsNone(result["GV-R92S128T"])

    def test_inspect_verified_variants(self):
        from llm_import.variant_evidence import inspect_variant_memory

        source = (
            "128MB(GV-R92S128T)/"
            "64MB(GV-R92S64T)"
        )

        result = inspect_variant_memory(
            source,
            ["GV-R92S128T", "GV-R92S64T"],
        )

        self.assertEqual(
            result["GV-R92S128T"]["status"],
            "VERIFIED",
        )
        self.assertEqual(
            result["GV-R92S128T"]["value_mb"],
            128,
        )
        self.assertEqual(
            result["GV-R92S64T"]["value_mb"],
            64,
        )

    def test_inspect_conflicting_variant(self):
        from llm_import.variant_evidence import inspect_variant_memory

        result = inspect_variant_memory(
            "128MB(GV-R92S128T) 256MB(GV-R92S128T)",
            ["GV-R92S128T"],
        )

        self.assertEqual(
            result["GV-R92S128T"]["status"],
            "CONFLICT",
        )
        self.assertEqual(
            result["GV-R92S128T"]["candidates_mb"],
            [128, 256],
        )

    def test_inspect_unknown_variant(self):
        from llm_import.variant_evidence import inspect_variant_memory

        result = inspect_variant_memory(
            "GV-R92S128T DDR memory",
            ["GV-R92S128T"],
        )

        self.assertEqual(
            result["GV-R92S128T"]["status"],
            "UNKNOWN",
        )

if __name__ == "__main__":
    unittest.main()