import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from unbundle import explode_profile, qualifying_segments, firm_node


def canon(t, corpus=None):
    return (t or "").lower().strip()


AMAZON = {
    "slug": "amazon",
    "company": "Amazon",
    "capability_tags": ["cloud-infrastructure", "e-commerce-marketplace", "fulfillment-and-last-mile"],
    "segments": [
        {"name": "AWS (Cloud & AI Services)", "weight": 0.18,
         "capability_tags": ["cloud-infrastructure", "ai-ml-platform"]},
        {"name": "North America Retail", "weight": 0.46,
         "capability_tags": ["e-commerce-marketplace", "fulfillment-and-last-mile"]},
        {"name": "Parks", "weight": 0.01,
         "capability_tags": ["theme-park-operations"]},
    ],
}


class QualifyTests(unittest.TestCase):
    def test_drops_single_tag_segments(self):
        segs = qualifying_segments(AMAZON)
        self.assertEqual(len(segs), 2)
        self.assertTrue(all(len(s["capability_tags"]) >= 2 for s in segs))


class ExplodeTests(unittest.TestCase):
    def test_splits_when_two_qualifying_segments(self):
        nodes = explode_profile(AMAZON, canon)
        self.assertEqual(len(nodes), 2)
        self.assertTrue(all(n["kind"] == "segment" for n in nodes))
        self.assertTrue(all(n["parent"] == "amazon" for n in nodes))
        tags = {t for n in nodes for t in n["capability_tags"]}
        self.assertNotIn("theme-park-operations", tags)

    def test_stays_a_firm_with_one_segment(self):
        rec = {
            "slug": "solo", "company": "Solo",
            "capability_tags": ["audit-and-assurance", "tax-advisory"],
            "segments": [{"name": "Audit", "capability_tags": ["audit-and-assurance", "tax-advisory"]}],
        }
        nodes = explode_profile(rec, canon)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["kind"], "firm")
        self.assertEqual(set(nodes[0]["capability_tags"]),
                         {"audit-and-assurance", "tax-advisory"})

    def test_firm_node_is_the_ticker(self):
        n = firm_node(AMAZON, canon)
        self.assertEqual(n["kind"], "firm")
        self.assertEqual(n["id"], "amazon")
        self.assertIn("cloud-infrastructure", n["capability_tags"])


if __name__ == "__main__":
    unittest.main()
