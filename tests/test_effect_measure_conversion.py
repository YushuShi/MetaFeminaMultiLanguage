import unittest

import pandas as pd

from effect_measure import (
    baseline_risk_for_disease,
    baseline_risk_from_percent,
    convert_ratio_to_rr,
    normalize_effect_type,
)
from meta_analysis import perform_meta_analysis


class EffectMeasureConversionTests(unittest.TestCase):
    def test_major_cancer_baseline_risks_are_disease_specific(self):
        self.assertEqual(baseline_risk_for_disease("Breast cancer"), 0.13)
        self.assertEqual(baseline_risk_for_disease("Ovarian cancer"), 0.013)
        self.assertEqual(baseline_risk_for_disease("Uterine cancer"), 0.031)
        self.assertEqual(baseline_risk_for_disease("Endometrial cancer"), 0.031)

    def test_subtype_percent_is_converted_to_probability(self):
        self.assertEqual(baseline_risk_from_percent(0.66), 0.0066)
        self.assertEqual(baseline_risk_from_percent(9.1), 0.091)

    def test_or_hr_and_irr_are_converted_to_rr(self):
        p0 = 0.031
        self.assertAlmostEqual(
            convert_ratio_to_rr(1.9, "OR", p0),
            1.9 / (1 - p0 + p0 * 1.9),
        )
        expected_rate_rr = (1 - (1 - p0) ** 1.9) / p0
        self.assertAlmostEqual(convert_ratio_to_rr(1.9, "HR", p0), expected_rate_rr)
        self.assertAlmostEqual(convert_ratio_to_rr(1.9, "IRR", p0), expected_rate_rr)
        self.assertEqual(convert_ratio_to_rr(1.9, "RR", p0), 1.9)
        self.assertEqual(normalize_effect_type("incidence rate ratio"), "IRR")

    def test_iron_uterine_regression_uses_three_point_one_percent(self):
        frame = pd.DataFrame([
            {"Study": "Study 1", "Effect Type": "RR", "Effect Size": 1.31, "Lower CI": 1.07, "Upper CI": 1.61},
            {"Study": "Study 2", "Effect Type": "OR", "Effect Size": 1.90, "Lower CI": 1.40, "Upper CI": 2.70},
            {"Study": "Study 3", "Effect Type": "OR", "Effect Size": 1.70, "Lower CI": 0.90, "Upper CI": 3.30},
            {"Study": "Study 4", "Effect Type": "OR", "Effect Size": 1.66, "Lower CI": 1.02, "Upper CI": 2.69},
        ])
        frame["SE"] = (frame["Upper CI"] - frame["Lower CI"]) / 3.92
        frame["Cases"] = 100
        frame["Sample Size"] = 1000

        result = perform_meta_analysis(
            frame,
            "Uterine cancer",
            "Iron",
            df_all=frame,
            generate_plots=False,
        )

        self.assertNotIn("error", result)
        self.assertEqual(result["headline"]["baseline_risk"], 0.031)
        self.assertAlmostEqual(result["headline"]["pooled_es"], 1.52, places=2)
        self.assertAlmostEqual(result["headline"]["i2"], 18.04, places=2)
        self.assertAlmostEqual(result["headline"]["tau2"], 0.01, places=2)


if __name__ == "__main__":
    unittest.main()
