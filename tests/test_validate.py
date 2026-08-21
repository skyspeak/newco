import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from validate import validate_one


def profile(**kwargs):
    base = {
        "slug": "acme",
        "_path": "acme.json",
        "company": "Acme",
        "domain": "acme.com",
        "activity_statements": [
            {"statement": f"does thing {i}", "source_url": "https://acme.com/about",
             "confidence": 0.8}
            for i in range(6)
        ],
        "capability_tags": [
            "parcel-sortation", "line-haul-network", "last-mile-delivery",
            "warehouse-operations", "fleet-operations", "customs-brokerage",
        ],
        "function_mix": [
            {"family": "warehouse-and-fulfillment-operations", "weight": 0.4},
            {"family": "drivers-and-delivery", "weight": 0.3},
            {"family": "software-engineering", "weight": 0.3},
        ],
        "value_chain": ["operate", "distribute"],
        "delivery_mode": ["physical-asset", "human-service"],
        "name_reality_gap": "Reads as a retailer; activity is a sortation network.",
        "sources": [{"url": "https://acme.com/about", "kind": "about-page"}],
        "extraction_notes": "Built from about page.",
        "extraction_confidence": 0.8,
    }
    base.update(kwargs)
    return base


class ValidateTests(unittest.TestCase):
    def test_good_profile(self):
        hard, soft = validate_one(profile())
        self.assertEqual(hard, [])
        self.assertEqual(soft, [])

    def test_slug_must_match_filename(self):
        hard, _ = validate_one(profile(_path="other.json"))
        self.assertTrue(any(v["kind"] == "slug_filename_mismatch" for v in hard))

    def test_invalid_value_chain_rejected(self):
        hard, _ = validate_one(profile(value_chain=["synergy"]))
        self.assertTrue(any(v["kind"] == "invalid_value_chain" for v in hard))

    def test_misplaced_advisory_is_warning(self):
        hard, soft = validate_one(profile(value_chain=["advisory", "service"]))
        self.assertFalse(any(v["kind"] == "invalid_value_chain" for v in hard))
        self.assertTrue(any(v["kind"] == "value_chain_looks_like_delivery_mode" for v in soft))

    def test_invalid_delivery_mode_rejected(self):
        hard, _ = validate_one(profile(delivery_mode=["vibes"]))
        self.assertTrue(any(v["kind"] == "invalid_delivery_mode" for v in hard))

    def test_few_statements_is_warning(self):
        stmts = [{"statement": "does one thing", "source_url": "https://acme.com",
                  "confidence": 0.7}]
        hard, soft = validate_one(profile(activity_statements=stmts))
        self.assertFalse(any(v["kind"] == "few_statements" for v in hard))
        self.assertTrue(any(v["kind"] == "few_statements" for v in soft))

    def test_statement_without_source_is_hard(self):
        stmts = [{"statement": "does a thing", "source_url": "", "confidence": 0.7}] * 6
        hard, _ = validate_one(profile(activity_statements=stmts))
        self.assertTrue(any(v["kind"] == "statement_missing_source" for v in hard))

    def test_person_in_notes_is_hard(self):
        hard, _ = validate_one(profile(
            extraction_notes="Founder Jane Smith said the company pivoted."))
        self.assertTrue(any(v["kind"] == "person" for v in hard))


if __name__ == "__main__":
    unittest.main()
