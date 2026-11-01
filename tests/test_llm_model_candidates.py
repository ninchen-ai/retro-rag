import unittest

from llm_import.model_candidates import detect_model_candidates


class TestModelCandidates(unittest.TestCase):

    def test_two_models(self):
        text = (
            "VGA Card GV-R92S128T / GV-R92S64T\n"
            "128MB(GV-R92S128T)/64MB(GV-R92S64T)"
        )

        self.assertEqual(
            detect_model_candidates(text),
            ["GV-R92S128T", "GV-R92S64T"],
        )

    def test_document_number_not_model(self):
        text = (
            "GV-R92S128T\n"
            "12MD-R92S128T-104"
        )

        self.assertEqual(
            detect_model_candidates(text),
            ["GV-R92S128T"],
        )

    def test_no_model_found(self):
        self.assertEqual(
            detect_model_candidates("ATI Radeon 9200SE"),
            [],
        )


if __name__ == "__main__":
    unittest.main()