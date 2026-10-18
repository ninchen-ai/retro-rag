import ast
import unittest
from pathlib import Path


class TestPdfImportStructure(unittest.TestCase):

    def test_store_outside_embedding_loop(self):
        source = Path("scripts/import_pdf.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)

        main = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "main"
        )

        embedding_loops = [
            node for node in ast.walk(main)
            if isinstance(node, ast.For)
            and any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "embedding"
                for statement in node.body
                for call in ast.walk(statement)
            )
        ]

        self.assertEqual(len(embedding_loops), 1)

        for loop in embedding_loops:
            self.assertFalse(any(
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "store"
                for statement in loop.body
                for call in ast.walk(statement)
            ))


if __name__ == "__main__":
    unittest.main()