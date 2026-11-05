"""Conservative grouping tests; originals always remain unchanged."""
import unittest

from experiments.pdf_span_groups import propose_span_groups


FIGURE = [{
    "class_name": "figure",
    "relation": "OVERLAPS_REGION",
    "bbox_pdf_points": [50, 50, 550, 400],
    "confidence": 0.9,
}]


def label(text, x0, y0, x1, y1, *, figure=FIGURE):
    return {
        "text": text,
        "bbox_pdf_points": [x0, y0, x1, y1],
        "size_pt": 12.0,
        "nearby_regions": figure,
    }


class SpanGroupTests(unittest.TestCase):
    def test_power_supply_vertical_group(self):
        rows = [
            label("POWER", 382.4, 98.4, 417.2, 111.6),
            label("SUPPLY", 382.4, 109.6, 419.4, 122.9),
        ]
        groups = propose_span_groups(rows)
        self.assertEqual([g["proposed_text"] for g in groups], ["POWER SUPPLY"])
        self.assertEqual([row["text"] for row in rows], ["POWER", "SUPPLY"])
        self.assertFalse(groups[0]["approved"])

    def test_distinct_same_baseline_labels_remain_separate(self):
        rows = [
            label("System Front", 206.9, 395.8, 282.4, 412.1),
            label("System Front", 441.7, 395.8, 517.2, 412.1),
        ]
        self.assertEqual(propose_span_groups(rows), [])

    def test_fan_vent_page41_remains_separate(self):
        # Confirmed negative reference from AGP Design Guide page 41.
        rows = [
            label("Fan", 273.5, 435.3, 306.3, 460.7),
            label("Vent", 263.0, 457.8, 302.9, 483.3),
        ]
        self.assertEqual(propose_span_groups(rows), [])

    def test_page41_power_supply_still_merges(self):
        rows = [
            label("Power", 452.2, 185.5, 507.6, 211.0),
            label("Supply", 452.2, 207.7, 513.9, 233.2),
        ]
        self.assertEqual(
            [item["proposed_text"] for item in propose_span_groups(rows)],
            ["Power Supply"]
        )

    def test_page41_open_area_still_merges(self):
        rows = [
            label("60% of area", 130.1, 625.6, 178.4, 638.9),
            label("open", 130.1, 637.6, 150.7, 651.4),
        ]
        self.assertEqual(
            [item["proposed_text"] for item in propose_span_groups(rows)],
            ["60% of area open"]
        )

    def test_different_figures_never_group(self):
        rows = [
            label("POWER", 100, 100, 150, 115),
            label("SUPPLY", 100, 112, 150, 127, figure=[{
                "class_name": "figure",
                "relation": "OVERLAPS_REGION",
                "bbox_pdf_points": [60, 100, 550, 500],
            }]),
        ]
        self.assertEqual(propose_span_groups(rows), [])

    def test_unaligned_multicolumn_no_group(self):
        rows = [
            label("POWER", 100, 100, 150, 115),
            label("SUPPLY", 200, 112, 250, 127),
        ]
        self.assertEqual(propose_span_groups(rows), [])


if __name__ == "__main__":
    unittest.main()
