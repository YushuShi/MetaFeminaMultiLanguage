import unittest

import pandas as pd

import meta_analysis


class CuratedExclusionTests(unittest.TestCase):
    def test_explicit_folate_exclusions_match_only_the_curated_context(self):
        for pmid in ("20574916", "25078601"):
            self.assertTrue(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Breast cancer", "folic_acid", "Incidence"
                )
            )
            self.assertFalse(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Breast cancer", "vitamin_b12", "Incidence"
                )
            )

    def test_filter_does_not_use_crowdsourced_exclusion_counts(self):
        frame = pd.DataFrame(
            [
                {"PMID": "20574916", "Effect Size": 2.03},
                {"PMID": "20410093", "Effect Size": 1.11},
            ]
        )

        filtered = meta_analysis.filter_curated_meta_analysis_exclusions(
            frame, "Breast cancer", "folic acid", "Incidence"
        )

        self.assertEqual(filtered["PMID"].tolist(), ["20410093"])


if __name__ == "__main__":
    unittest.main()
