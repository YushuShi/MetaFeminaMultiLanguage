import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from subcategory_analysis import _localized_exposure, build_subcategory_outputs


class SubcategoryAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.annotations = self.root / "subcategory_annotations.json"
        self.results = self.root / "results"
        self.plots = self.root / "plots"
        self.cache = self.root / "Cached_results"
        self.cache.mkdir()
        self.registry_csv = self.root / "registry.csv"
        self.registry_csv.write_text("placeholder\n", encoding="utf-8")
        module = types.ModuleType("subcategory_registry")
        module.load_registry = lambda _path: [
            {
                "subcategory_id": "breast_triple_negative_breast_cancer",
                "major_site_id": "breast",
                "subcategory_slug": "triple_negative_breast_cancer",
                "label": "Triple-negative breast cancer",
                "estimated_lifetime_probability_us_women_percent": 1.3,
            }
        ]
        self.old_registry = sys.modules.get("subcategory_registry")
        sys.modules["subcategory_registry"] = module

    def tearDown(self):
        if self.old_registry is None:
            sys.modules.pop("subcategory_registry", None)
        else:
            sys.modules["subcategory_registry"] = self.old_registry
        self.tempdir.cleanup()

    def _write_annotations(self, status="reported_separate_estimate", known_context=True):
        context_id = "ctx-1" if known_context else "not-saved"
        payload = {
            "contexts": [{"context_id": "ctx-1", "exposure": "Coffee", "study": {"Study": "Doe et al. (2020)", "PMID": "1"}}],
            "annotations": [{
                "context_id": context_id,
                "major_outcomes": [{
                    "major_site_id": "breast",
                    "subcategory_outcomes": [{
                        "subcategory_id": "breast_triple_negative_breast_cancer",
                        "status": status,
                        "effect_estimate": {"effect_size": 0.8, "lower_ci": 0.7, "upper_ci": 0.9, "effect_type": "RR"},
                    }],
                }],
            }],
        }
        self.annotations.write_text(json.dumps(payload), encoding="utf-8")

    def _build(self):
        return build_subcategory_outputs(
            self.annotations, self.results, self.plots, self.registry_csv, self.cache
        )

    def test_summary_exposure_labels_translate_from_canonical_names_or_slugs(self):
        self.assertEqual(_localized_exposure("Vitamin A", "zh-CN"), "维生素 A")
        self.assertEqual(_localized_exposure("vitamin_a", "zh-TW"), "維生素 A")
        self.assertEqual(_localized_exposure("mushrooms", "nl"), "Paddenstoelen")
        self.assertEqual(_localized_exposure("Vitamin A", "ko"), "비타민 A")
        self.assertEqual(
            _localized_exposure("Vitamins A, C, D, E, K", "ko"),
            "비타민 A, C, D, E, K",
        )
        self.assertEqual(_localized_exposure("Vitamin A"), "Vitamin A")

    def test_builds_isolated_result_and_placeholder_diagnostics(self):
        stale_result = self.results / "breast" / "triple_negative_breast_cancer" / "stale.json"
        stale_plot = self.plots / "breast" / "triple_negative_breast_cancer" / "stale.png"
        stale_result.parent.mkdir(parents=True)
        stale_plot.parent.mkdir(parents=True)
        stale_result.write_text("{}", encoding="utf-8")
        stale_plot.write_bytes(b"stale")
        self._write_annotations()
        manifest = self._build()
        result = json.loads((self.results / "breast" / "triple_negative_breast_cancer" / "coffee.json").read_text())
        self.assertEqual(manifest["result_count"], 1)
        self.assertEqual(result["headline"]["n_studies"], 1)
        self.assertEqual(result["scope"]["estimated_lifetime_probability_us_women_percent"], 1.3)
        self.assertTrue((self.root / result["plot_urls"]["forest"]).is_file())
        self.assertFalse(result["availability"]["baujat"]["available"])
        self.assertEqual(result["availability"]["baujat"]["reason"], "baujat_requires_3_studies")
        self.assertTrue((self.plots / "breast" / "triple_negative_breast_cancer" / "summary_manifest.json").is_file())
        ui_manifest = json.loads((self.plots / "summary_manifest.json").read_text())
        summary_plot = ui_manifest["scopes"]["breast"]["subcategories"]["triple_negative_breast_cancer"]["plots"]["forest-protective"]
        self.assertIn("filename", summary_plot)
        self.assertFalse(summary_plot["available"])
        self.assertEqual(summary_plot["reason"], "no_protective_eligible_exposures")
        summary_folder = self.plots / "breast" / "triple_negative_breast_cancer"
        for locale in ("zh-CN", "zh-TW", "nl", "ko"):
            locale_folder = summary_folder / "locales" / locale
            for filename in (
                "forest_protective.pdf", "forest_harmful.pdf",
                "effect_size_vs_i2.pdf", "egger_vs_i2.pdf",
            ):
                self.assertTrue((locale_folder / filename).is_file())
        self.assertFalse(stale_result.exists())
        self.assertFalse(stale_plot.exists())

    def test_never_promotes_nonseparate_or_unknown_context_estimates(self):
        self._write_annotations(status="reported_no_separate_estimate")
        manifest = self._build()
        self.assertEqual(manifest["result_count"], 1)  # explicit unavailable result, not a silent omission
        self.assertEqual(manifest["eligible_estimate_count"], 0)
        result = json.loads((self.results / "breast" / "triple_negative_breast_cancer" / "coffee.json").read_text())
        self.assertEqual(result["availability"]["eligible_study_count"], 0)

        self._write_annotations(known_context=False)
        manifest = self._build()
        self.assertEqual(manifest["eligible_estimate_count"], 0)
        self.assertIn("unknown_context_id", [item["reason"] for item in manifest["skipped_annotations"]])

    def test_reads_append_only_event_ledger_and_context_source_index(self):
        sources = {
            "context_index": {
                "ctx-1": {
                    "context_id": "ctx-1", "major_site_id": "breast", "exposure": "Tea",
                    "effect_size": 9, "lower_ci": 8, "upper_ci": 10, "effect_type": "OR",
                }
            },
            "sources": {"10": {"pmid": "10", "title": "Saved article", "contexts": ["ctx-1"]}},
        }
        self.annotations.with_name("subcategory_sources.json").write_text(json.dumps(sources), encoding="utf-8")
        event = {
            "schema_version": 1,
            "events": [{
                "event_id": "event-1", "created_at": "2026-08-04T00:00:00Z", "pmid": "10", "stage": "terra", "status": "complete", "source_hash": "source-1",
                "result": {"pmid": "10", "major_outcomes": [{"major_site_id": "breast", "general_outcome_reported": True, "subcategory_outcomes": [{
                    "subcategory_id": "breast_triple_negative_breast_cancer", "status": "reported_separate_estimate", "estimates": [{
                        "context_id": "ctx-1", "effect_size": 0.75, "lower_ci": 0.60, "upper_ci": 0.95, "effect_type": "RR"
                    }]
                }]}]},
            }],
        }
        self.annotations.write_text(json.dumps(event), encoding="utf-8")
        cache_file = self.cache / "tea" / "breast_cancer_incidence_true_core.json"
        cache_file.parent.mkdir()
        cache_file.write_text(json.dumps({"studies": [{
            "PMID": "10",
            "Study": "Doe AB et al. (2020) [PMID: 10]",
            "Authors": "Doe AB, Roe CD",
            "Journal": "Journal of Saved Studies",
            "Year": "2020",
            "Reference": "Saved article",
            "exposure_measurement_type": "human_biospecimen",
            "exposure_measurement_supporting_text": "Tea exposure was measured in plasma.",
        }]}), encoding="utf-8")
        self._build()
        result = json.loads((self.results / "breast" / "triple_negative_breast_cancer" / "tea.json").read_text())
        self.assertEqual(result["studies"][0]["pmid"], "10")
        self.assertEqual(result["studies"][0]["study"], "Doe AB et al. (2020) [PMID: 10]")
        self.assertEqual(result["studies"][0]["Authors"], "Doe AB, Roe CD")
        self.assertEqual(result["studies"][0]["Journal"], "Journal of Saved Studies")
        self.assertEqual(result["studies"][0]["Year"], "2020")
        self.assertEqual(result["studies"][0]["Reference"], "Saved article")
        self.assertEqual(result["studies"][0]["exposure_measurement_type"], "human_biospecimen")
        self.assertEqual(
            result["studies"][0]["exposure_measurement_supporting_text"],
            "Tea exposure was measured in plasma.",
        )
        self.assertEqual(result["studies"][0]["effect_size"], 0.75)


if __name__ == "__main__":
    unittest.main()
