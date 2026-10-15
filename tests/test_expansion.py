import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from merge_expansion import assign_cluster


class AssignClusterTests(unittest.TestCase):
    def setUp(self):
        self.bags = {
            0: {"grocery-retail-operations": 10, "inventory-management": 8},
            9: {"theme-park-operations": 12, "film-and-television-production": 4},
            10: {"competitive-pricing-intelligence": 9, "field-service-merchandising": 8,
                 "product-attribute-data": 5},
        }

    def test_pricing_intel_goes_to_field_cluster_not_stale_id(self):
        cid = assign_cluster(
            ["competitive-pricing-intelligence", "product-attribute-data"],
            self.bags, fallback=9)
        self.assertEqual(cid, 10)

    def test_theme_parks_stay_in_entertainment(self):
        cid = assign_cluster(["theme-park-operations"], self.bags, fallback=0)
        self.assertEqual(cid, 9)

    def test_no_overlap_uses_fallback(self):
        cid = assign_cluster(["unrelated-widget-fabrication"], self.bags, fallback=4)
        self.assertEqual(cid, 4)

    def test_exclusive_signature_beats_portable_overlap(self):
        bags = {
            4: {"revenue-management-and-pricing": 10, "hotel-management-contracts": 9},
            9: {"theme-park-operations": 12},
        }
        cid = assign_cluster(["theme-park-operations"], bags, fallback=4)
        self.assertEqual(cid, 9)


if __name__ == "__main__":
    unittest.main()
