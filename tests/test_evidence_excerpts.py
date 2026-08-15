import json
import unittest
from pathlib import Path

from scripts.audit_evidence_excerpts import ROOT, scan_preferred_caches


class EvidenceExcerptTests(unittest.TestCase):
    def test_default_ui_never_shows_numeric_values_with_blank_support(self):
        gaps = scan_preferred_caches()
        self.assertEqual(
            gaps,
            [],
            msg="\n".join(
                f"{gap.exposure} PMID {gap.pmid}: {', '.join(gap.missing_fields)}"
                for gap in gaps
            ),
        )

    def test_quarantined_rows_are_preserved_outside_served_caches(self):
        quarantine_path = ROOT / "data" / "evidence_review_quarantine.json"
        payload = json.loads(quarantine_path.read_text(encoding="utf-8"))
        records = payload["records"]

        self.assertEqual(len(records), 50)
        self.assertTrue(all(record.get("study") for record in records))
        self.assertTrue(all(record.get("reason_code") for record in records))
        self.assertIn(
            ("vitamin_e", "9498489", "wrong_metric"),
            {
                (record["exposure"], record["pmid"], record["reason_code"])
                for record in records
            },
        )

    def test_alcohol_effect_modifier_is_not_served_as_folic_acid(self):
        folic_acid_cache = json.loads((
            ROOT / "Cached_results" / "folic_acid"
            / "breast_cancer_incidence_true_all.json"
        ).read_text(encoding="utf-8"))
        alcohol_cache = json.loads((
            ROOT / "Cached_results" / "alcohol"
            / "breast_cancer_incidence_true_core.json"
        ).read_text(encoding="utf-8"))

        self.assertNotIn(
            "20155314",
            {str(study.get("PMID")) for study in folic_acid_cache["studies"]},
        )
        self.assertNotIn("20155314", json.dumps(folic_acid_cache))
        self.assertEqual(len(folic_acid_cache["studies"]), 37)
        self.assertEqual(
            {
                key: folic_acid_cache["headline"][key]
                for key in ("pooled_es", "ci_low", "ci_upp", "pi_low", "pi_upp")
            },
            {
                "pooled_es": 0.81,
                "ci_low": 0.73,
                "ci_upp": 0.9,
                "pi_low": 0.48,
                "pi_upp": 1.37,
            },
        )
        self.assertIn(
            "pooled analysis of 36 studies",
            folic_acid_cache["headline"]["results_interpretation"],
        )
        self.assertIn(
            "20155314",
            {str(study.get("PMID")) for study in alcohol_cache["studies"]},
        )

        quarantine = json.loads((
            ROOT / "data" / "evidence_review_quarantine.json"
        ).read_text(encoding="utf-8"))["records"]
        record = next(
            row for row in quarantine
            if row["exposure"] == "folic_acid" and row["pmid"] == "20155314"
        )
        self.assertEqual(record["reason_code"], "wrong_exposure")
        self.assertIn("alcohol", record["note"].lower())

    def test_phosphorus_sample_size_has_primary_source_support(self):
        cache_path = (
            ROOT / "Cached_results" / "phosphorus"
            / "breast_cancer_incidence_true_all.json"
        )
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        study = next(
            row for row in payload["studies"]
            if str(row.get("PMID")) == "37686766"
        )

        support = study["extraction_supporting_text"]["sample_size"]
        self.assertIn("74 breast cancer cases", support)
        self.assertIn("296 controls", support)
        self.assertEqual(
            study["evidence_excerpt_source"],
            "https://pmc.ncbi.nlm.nih.gov/articles/PMC10490459/",
        )

    def test_rosenberg_subtype_totals_include_cases_and_shared_controls(self):
        expected = {
            "invasive_ductal_carcinoma": {"cases": 1888, "sample_size": 4953},
            "invasive_lobular_carcinoma": {"cases": 308, "sample_size": 3373},
        }

        for subtype, values in expected.items():
            result_path = (
                ROOT / "data" / "subcategory_results" / "breast"
                / subtype / "alcohol.json"
            )
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            study = next(
                row for row in payload["studies"]
                if str(row.get("PMID")) == "16507159"
            )

            self.assertEqual(study["Cases"], values["cases"])
            self.assertEqual(study["Sample Size"], values["sample_size"])
            support = study["extraction_supporting_text"]["sample_size"]
            self.assertIn("invasive ductal (n = 1,888)", support)
            self.assertIn("lobular (n = 308)", support)
            self.assertIn("3,065 age-frequency matched controls", support)

    def test_removed_row_source_audit_covers_every_unique_quarantine_context(self):
        quarantine = json.loads(
            (ROOT / "data" / "evidence_review_quarantine.json").read_text(
                encoding="utf-8"
            )
        )["records"]
        audit = json.loads(
            (ROOT / "data" / "removed_rows_source_audit_2026-08-14.json")
            .read_text(encoding="utf-8")
        )["rows"]

        quarantined_contexts = {
            (
                record["exposure"],
                record["disease"],
                str(record["study"]["PMID"]),
            )
            for record in quarantine
        }
        audited_contexts = {
            (row["exposure"], row["cancer_context"], row["pmid"])
            for row in audit
        }

        self.assertEqual(len(quarantine), 50)
        self.assertEqual(len(quarantined_contexts), 47)
        self.assertEqual(audited_contexts, quarantined_contexts)
        self.assertEqual(
            [row["row_number"] for row in audit],
            list(range(1, 48)),
        )
        self.assertTrue(
            all(
                row["first_author_last_name"]
                and row["source_excerpt"]
                and row["source_url"].startswith("https://")
                for row in audit
            )
        )


if __name__ == "__main__":
    unittest.main()
