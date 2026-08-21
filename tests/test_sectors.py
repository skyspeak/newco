import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from sectors import sector_from_labels, sector_from_tags


class SectorFromLabelsTests(unittest.TestCase):
    def test_empty_is_none(self):
        self.assertIsNone(sector_from_labels([]))
        self.assertIsNone(sector_from_labels(None))

    def test_hospital_label(self):
        self.assertEqual(sector_from_labels(["Hospitals & Health Care"]),
                         "healthcare-provider")

    def test_software_label(self):
        self.assertEqual(sector_from_labels(["Software Development"]), "technology")

    def test_first_match_wins_on_short_labels(self):
        # hospitality before healthcare so "hospitality" is not swallowed by hospital
        self.assertEqual(sector_from_labels(["Hospitality"]), "hospitality-travel")


class SectorFromTagsTests(unittest.TestCase):
    def test_empty_is_unclassified(self):
        self.assertEqual(sector_from_tags([]), "unclassified")

    def test_hospital_beats_incidental_software(self):
        tags = [
            "clinical-care-delivery", "hospital-operations", "patient-care",
            "software-engineering",  # almost every large firm has this
        ]
        self.assertEqual(sector_from_tags(tags), "healthcare-provider")

    def test_hilton_is_hospitality_not_healthcare(self):
        tags = ["hotel-operations", "guest-experience", "loyalty-programs",
                "revenue-management-and-pricing"]
        self.assertEqual(sector_from_tags(tags), "hospitality-travel")

    def test_cloud_platform_is_technology(self):
        tags = ["cloud-infrastructure-services", "developer-platform",
                "ai-and-machine-learning"]
        self.assertEqual(sector_from_tags(tags), "technology")

    def test_tie_is_unclassified(self):
        # equal scores on two sectors should not pick a winner
        tags = ["clinical-care-delivery", "hotel-operations"]
        # both patterns are weight-3 single hits — a tie must not pretend certainty
        self.assertEqual(sector_from_tags(tags), "unclassified")


if __name__ == "__main__":
    unittest.main()
