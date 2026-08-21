import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from privacy import find_violations, scrub


def rec(**kwargs):
    base = {
        "slug": "acme",
        "company": "Acme",
        "activity_statements": [
            {"statement": "operates a domestic parcel sortation network",
             "source_url": "https://example.com/about", "confidence": 0.9}
        ],
        "name_reality_gap": "none",
        "extraction_notes": "",
        "sources": [{"url": "https://example.com/about", "kind": "about-page"}],
    }
    base.update(kwargs)
    return base


class PrivacyTests(unittest.TestCase):
    def test_clean_record(self):
        self.assertEqual(find_violations(rec()), [])

    def test_email_is_hard_fail(self):
        v = find_violations(rec(extraction_notes="contact jane@acme.com for press"))
        self.assertTrue(any(x["kind"] == "email" for x in v))

    def test_phone_is_hard_fail(self):
        v = find_violations(rec(name_reality_gap="call 415-555-0100"))
        self.assertTrue(any(x["kind"] == "phone" for x in v))

    def test_named_executive_is_hard_fail(self):
        v = find_violations(rec(
            activity_statements=[{"statement": "CEO Jane Smith said the network doubled",
                                  "source_url": "https://example.com", "confidence": 0.8}]))
        self.assertTrue(any(x["kind"] == "person" for x in v))

    def test_missing_source_is_hard_fail(self):
        v = find_violations(rec(sources=[]))
        self.assertTrue(any(x["kind"] == "no_provenance" for x in v))

    def test_job_family_without_person_is_allowed(self):
        v = find_violations(rec(
            activity_statements=[{"statement": "staffs actuarial, claims adjudication, and catastrophe modeling",
                                  "source_url": "https://example.com", "confidence": 0.9}]))
        self.assertFalse(any(x["kind"] == "person" for x in v))

    def test_scrub_aggregates(self):
        out = scrub([rec(), rec(slug="bad", sources=[])])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["slug"], "bad")


if __name__ == "__main__":
    unittest.main()
