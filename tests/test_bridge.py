import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from bridge import jaccard, bridge_score, neighbors_for, incumbents, count_desk_hits, scrub_row
from merge_expansion import assign_cluster
from privacy import find_violations


class JaccardTests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(jaccard(["a", "b"], ["b", "a"]), 1.0)

    def test_empty(self):
        self.assertEqual(jaccard([], ["a"]), 0.0)

    def test_partial(self):
        self.assertAlmostEqual(jaccard(["a", "b"], ["b", "c"]), 1 / 3)


class ScoreTests(unittest.TestCase):
    def test_no_shared_is_zero(self):
        s, shared = bridge_score(["claims-adjudication"], ["theme-park-operations"], True)
        self.assertEqual(s, 0.0)
        self.assertEqual(shared, [])

    def test_mortgage_newco_prefers_rocket_over_park(self):
        tags = ["digital-mortgage-origination", "consumer-lending", "loan-servicing"]
        rocket = ["digital-mortgage-origination", "consumer-lending", "loan-servicing",
                  "fintech-product-development"]
        disney = ["theme-park-operations", "film-and-tv-production", "content-distribution"]
        a, _ = bridge_score(tags, rocket, True)
        b, _ = bridge_score(tags, disney, False)
        self.assertGreater(a, b)

    def test_coverage_beats_tiny_jaccard_on_fat_incumbent(self):
        new = ["fulfillment-network", "inventory-management"]
        amazon = ["fulfillment-network", "inventory-management", "cloud", "ads", "chips",
                  "streaming", "pharmacy", "devices", "marketplace", "seller-platform"]
        s, shared = bridge_score(new, amazon, False)
        self.assertGreater(s, 0.2)
        self.assertEqual(shared, ["fulfillment-network", "inventory-management"])


class NeighborMixTests(unittest.TestCase):
    def test_keeps_seed_incumbents_in_top_hits(self):
        pool = [
            {"slug": "off-1", "name": "Obscure 3PL", "kind": "off", "cluster": 0,
             "parent": "off-1",
             "tags": ["fulfillment-network", "inventory-management"]},
            {"slug": "walmart", "name": "Walmart", "kind": "seed", "cluster": 0,
             "parent": "walmart",
             "tags": ["fulfillment-network", "inventory-management", "store-network"]},
            {"slug": "disney", "name": "Disney", "kind": "seed", "cluster": 9,
             "parent": "disney",
             "tags": ["theme-park-operations"]},
        ]
        nbrs = neighbors_for(["fulfillment-network", "inventory-management"], 0, pool, k=2)
        slugs = [n["slug"] for n in nbrs]
        self.assertIn("walmart", slugs)

    def test_fulfillment_newco_hits_retail_line_not_cloud_line(self):
        pool = [
            {"slug": "amazon::aws-cloud-ai-services", "name": "Amazon · AWS",
             "kind": "line", "parent": "amazon", "cluster": 2,
             "tags": ["cloud-infrastructure-services", "ai-ml-platform"]},
            {"slug": "amazon::north-america-retail", "name": "Amazon · Retail",
             "kind": "line", "parent": "amazon", "cluster": 0,
             "tags": ["fulfillment-network", "inventory-management",
                      "e-commerce-marketplace"]},
        ]
        nbrs = neighbors_for(
            ["fulfillment-network", "robotics-fulfillment"], 0, pool, k=1)
        self.assertEqual(nbrs[0]["slug"], "amazon::north-america-retail")

    def test_caps_two_lines_per_parent(self):
        pool = [
            {"slug": f"amazon::{i}", "name": f"Amazon · {i}", "kind": "line",
             "parent": "amazon", "cluster": 0,
             "tags": ["fulfillment-network"]}
            for i in range(5)
        ]
        nbrs = neighbors_for(["fulfillment-network"], 0, pool, k=5)
        self.assertEqual(len(nbrs), 2)


class IncumbentPoolTests(unittest.TestCase):
    def test_line_nodes_replace_ticker_bags(self):
        m = {
            "companies": [{"slug": "amazon", "company": "Amazon", "cluster": 2, "tags": ["cloud", "fulfillment-network"]}],
            "expansion": [],
        }
        lines = [{
            "id": "amazon::retail", "name": "Amazon · Retail", "kind": "segment",
            "parent": "amazon", "tags": ["fulfillment-network"],
        }]
        pool = incumbents(m, lines)
        slugs = {p["slug"] for p in pool}
        self.assertIn("amazon::retail", slugs)
        self.assertNotIn("amazon", slugs)

    def test_desk_hit_counts_line_not_ticker(self):
        kept = [
            {"neighbors": [{"kind": "line", "name": "GM · GMNA"}]},
            {"neighbors": [{"kind": "seed", "name": "Rocket Companies"}]},
            {"neighbors": []},
        ]
        self.assertEqual(count_desk_hits(kept), 1)


class PrivacyTests(unittest.TestCase):
    def test_firm_level_row_is_clean(self):
        viol = scrub_row({
            "company": "Haladir",
            "activity_evidence": "Sits on warehouse-management systems and turns that data into routing decisions.",
            "bridge": "A logistics decision layer, not a new retailer.",
            "source_url": "https://www.ycombinator.com/companies/haladir",
        })
        self.assertFalse(any(v["kind"] in ("email", "phone", "person") for v in viol))

    def test_founder_sentence_is_dropped_by_privacy(self):
        rec = {
            "company": "BadCo",
            "activity_statements": ["Founder Jane Smith said the warehouse ships overnight."],
            "source_url": "https://example.com",
        }
        kinds = {v["kind"] for v in find_violations(rec)}
        self.assertIn("person", kinds)


class ClusterAssignTests(unittest.TestCase):
    def test_haladir_lands_in_store_network_cluster(self):
        bags = {
            0: {"inventory-management": 10, "fulfillment-network": 9},
            2: {"semiconductor-design": 12},
        }
        cid = assign_cluster(
            ["inventory-management", "fulfillment-network"], bags, fallback=2)
        self.assertEqual(cid, 0)


if __name__ == "__main__":
    unittest.main()
