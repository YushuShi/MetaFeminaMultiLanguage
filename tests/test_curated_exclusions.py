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

    def test_genotype_and_family_history_records_are_globally_excluded(self):
        for pmid in ("30624689", "16599372", "8547538"):
            self.assertTrue(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Breast cancer", "vitamin_e", "Incidence"
                )
            )
            self.assertTrue(
                meta_analysis.is_curated_meta_analysis_exclusion(
                    pmid, "Uterine cancer", "vitamin_e", "Incidence"
                )
            )

    def test_mendelian_randomization_records_are_removed_from_meta_analysis(self):
        frame = pd.DataFrame([
            {
                "PMID": "mr-study",
                "Design": "Two-sample Mendelian randomization",
                "Reference": "A causal analysis",
            },
            {
                "PMID": "genetic-proxy-study",
                "Reference": "Genetically predicted nutrient levels and cancer risk",
            },
            {
                "PMID": "instrumental-variable-study",
                "Reference": "Causal associations between blood metabolites and cancer",
                "exposure_measurement_supporting_text": "Instrumental variables were selected from GWAS data.",
            },
            {
                "PMID": "observational-study",
                "Design": "Prospective cohort",
                "Reference": "Dietary exposure and cancer risk",
            },
        ])

        filtered = meta_analysis.filter_curated_meta_analysis_exclusions(
            frame, "Breast cancer", "vitamin_e", "Incidence"
        )

        self.assertEqual(filtered["PMID"].tolist(), ["observational-study"])

    def test_curated_vitamin_e_and_antioxidant_exclusions(self):
        for pmid in ("12131659", "12891146", "2399562", "30373451"):
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

    def test_dietary_measurement_corrections_are_saved_after_exclusions(self):
        cache_path = (
            Path(__file__).resolve().parents[1]
            / "Cached_results"
            / "vitamin_e"
            / "breast_cancer_incidence_true_all.json"
        )
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        by_pmid = {str(study.get("PMID")): study for study in payload["studies"]}

        for pmid in ("11713032", "19358284"):
            self.assertEqual(by_pmid[pmid]["exposure_measurement_type"], "dietary_intake")

        self.assertTrue({"30624689", "16599372", "8547538"}.isdisjoint(by_pmid))


if __name__ == "__main__":
    unittest.main()
