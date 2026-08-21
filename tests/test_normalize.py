import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from normalize import canon_tag, canon_family, toks, coerce_vocabs


class CanonTagTests(unittest.TestCase):
    def test_synonym_collapses_loyalty(self):
        self.assertEqual(canon_tag("loyalty-program"), "loyalty-programs")
        self.assertEqual(canon_tag("customer-loyalty"), "loyalty-programs")

    def test_suffix_stripped_only_when_stem_exists(self):
        # "wealth-management" must NOT degrade to "wealth"
        self.assertEqual(canon_tag("wealth-management"), "wealth-management")
        # but "logistics-ops" collapses when the stem is a known synonym
        self.assertEqual(canon_tag("logistics-ops"), "logistics-network")

    def test_suffix_stripped_against_corpus(self):
        # Use a stem that is not itself a synonym-table key, otherwise the
        # lookup maps the stripped form back to a longer canonical tag.
        corpus = {"inventory"}
        self.assertEqual(canon_tag("inventory-operations", corpus), "inventory")

    def test_empty(self):
        self.assertEqual(canon_tag(""), "")
        self.assertEqual(canon_tag("???"), "")


class CanonFamilyTests(unittest.TestCase):
    def test_software_variants(self):
        self.assertEqual(canon_family("software-development"), "software-engineering")
        self.assertEqual(canon_family("Technology"), "software-engineering")

    def test_unknown_family_is_slugified_not_dropped(self):
        self.assertEqual(canon_family("Actuarial Modeling"), "actuarial-modeling")


class CoerceVocabTests(unittest.TestCase):
    def test_advisory_moves_to_delivery_mode(self):
        vc, dm = coerce_vocabs(["advisory"], ["human-service"])
        self.assertEqual(vc, ["service"])
        self.assertEqual(dm, ["advisory", "human-service"])

    def test_content_moves_without_dropping_real_chain(self):
        vc, dm = coerce_vocabs(["design", "content"], ["software"])
        self.assertEqual(vc, ["design"])
        self.assertEqual(dm, ["content", "software"])


class TokenTests(unittest.TestCase):
    def test_stopwords_dropped(self):
        words = toks("operates a leading global customer experience platform")
        self.assertNotIn("leading", words)
        self.assertNotIn("global", words)
        self.assertIn("platform", words)


if __name__ == "__main__":
    unittest.main()
