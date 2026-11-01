import unittest

from scripts.import_llm import (
    load_schema,
    build_extraction_schema,
    render_markdown,
)


class TestOperatingSystemSchema(unittest.TestCase):

    def test_os_fields_are_separate(self):
        schema = load_schema("grafikkarte")

        for field in (
            "minimum_os_requirements",
            "supported_operating_systems",
            "drivers",
        ):
            self.assertIn(field, schema["fields"])
            self.assertEqual(
                schema["fields"][field]["type"],
                "list",
            )

    def test_llm_schema_contains_os_fields(self):
        schema = load_schema("grafikkarte")
        extraction_schema = build_extraction_schema(schema)

        properties = extraction_schema["properties"]["specs"]["properties"]

        for field in (
            "minimum_os_requirements",
            "supported_operating_systems",
            "drivers",
        ):
            self.assertIn(field, properties)

    def test_markdown_keeps_os_categories_separate(self):
        schema = load_schema("grafikkarte")

        specs = {
            field: (
                [] if definition["type"] == "list"
                else None
            )
            for field, definition in schema["fields"].items()
        }

        specs["minimum_os_requirements"] = ["Windows 98"]
        specs["supported_operating_systems"] = ["Windows XP"]
        specs["drivers"] = ["Radeon Display Driver"]

        markdown = render_markdown(
            "grafikkarte",
            "Gigabyte",
            "GV-R92S128T",
            specs,
        )

        self.assertIn("## Betriebssystemanforderungen", markdown)
        self.assertIn("## Unterstützte Betriebssysteme", markdown)
        self.assertIn("## Treiber", markdown)
        self.assertIn("Windows 98", markdown)
        self.assertIn("Windows XP", markdown)
        self.assertIn("Radeon Display Driver", markdown)


if __name__ == "__main__":
    unittest.main()