import json
import unittest
from pathlib import Path

import pandas as pd

import meta_analysis


class CuratedExclusionTests(unittest.TestCase):
    def test_explicit_folate_exclusions_match_only_the_curated_context(self):
        for pmid in ("20030812", "20574916", "25078601"):
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
                {"PMID": "20030812", "Effect Size": 0.6173},
                {"PMID": "20574916", "Effect Size": 2.03},
                {"PMID": "20410093", "Effect Size": 1.11},
            ]
        )

        filtered = meta_analysis.filter_curated_meta_analysis_exclusions(
            frame, "Breast cancer", "folic acid", "Incidence"
        )

        self.assertEqual(filtered["PMID"].tolist(), ["20410093"])

    def test_curated_vitamin_e_and_antioxidant_exclusions(self):
        for pmid in ("12131659", "12891146", "30373451"):
            self.assertTrue(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Breast cancer", "vitamin_e", "Incidence"
                )
            )
            self.assertFalse(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Breast cancer", "alcohol", "Incidence"
                )
            )

        self.assertTrue(
            meta_analysis.is_curated_meta_analysis_exclusion(
                "14659342", "Breast cancer", "vitamin_e", "Incidence"
            )
        )
        self.assertTrue(
            meta_analysis.is_curated_meta_analysis_exclusion(
                "14659342", "Breast cancer", "antioxidants", "Incidence"
            )
        )

    def test_male_breast_cancer_records_are_excluded_only_from_alcohol_context(self):
        for pmid in ("15280636", "25515550", "28225200"):
            self.assertTrue(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Breast cancer", "alcohol", "Incidence"
                )
            )
            self.assertFalse(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Breast cancer", "vitamin_e", "Incidence"
                )
            )

    def test_dietary_measurement_corrections_and_zhu_excerpts_are_saved(self):
        cache_path = (
            Path(__file__).resolve().parents[1]
            / "Cached_results"
            / "vitamin_e"
            / "breast_cancer_incidence_true_all.json"
        )
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        by_pmid = {str(study.get("PMID")): study for study in payload["studies"]}

        for pmid in ("11713032", "16599372", "19358284"):
            self.assertEqual(by_pmid[pmid]["exposure_measurement_type"], "dietary_intake")

        zhu_support = by_pmid["16599372"]["extraction_supporting_text"]
        for field in (
            "sample_size",
            "effect_size",
            "effect_direction",
            "p_value",
            "confidence_interval",
            "outcome_definition",
            "exposure_definition",
        ):
            self.assertTrue(zhu_support[field])


if __name__ == "__main__":
    unittest.main()
