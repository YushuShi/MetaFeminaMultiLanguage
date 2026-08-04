import importlib.util
import json
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from subcategory_registry import REGISTRY, load_registry

SCRIPT = ROOT / "scripts" / "enrich_subcategories.py"
SPEC = importlib.util.spec_from_file_location("enrich_subcategories", SCRIPT)
enrich = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(enrich)


class SubcategoryRegistryTests(unittest.TestCase):
    def test_registry_has_stable_ids_and_lifetime_risks(self):
        self.assertEqual(len(REGISTRY.subcategories), 17)
        breast = REGISTRY.by_id["breast_invasive_ductal_carcinoma"]
        self.assertEqual(breast.major_site_id, "breast")
        self.assertEqual(breast.estimated_lifetime_probability_us_women_percent, 9.1)
        self.assertTrue(REGISTRY.is_known_subcategory("ovary_high_grade_serous_carcinoma", "ovary"))
        self.assertFalse(REGISTRY.is_known_subcategory("ovary_high_grade_serous_carcinoma", "breast"))

    def test_registry_csv_is_validated(self):
        self.assertEqual(load_registry().to_dict()["schema_version"], 1)

    def test_model_result_rejects_unknown_category_and_context(self):
        source = {"pmid": "1"}
        contexts = [{"context_id": "1|breast|coffee|0", "major_site_id": "breast", "cached_study": {}}]
        bad = {"pmid": "1", "major_outcomes": [{"major_site_id": "breast", "general_outcome_reported": True, "subcategory_outcomes": [{"subcategory_id": "not_real", "status": "reported_no_separate_estimate", "evidence_text": "x", "needs_full_text": False, "estimates": []}]}]}
        with self.assertRaises(ValueError):
            enrich.validate_result(bad, source, contexts)

    def test_model_result_accepts_known_subtype_estimate(self):
        source = {"pmid": "1"}
        contexts = [{"context_id": "1|breast|coffee|0", "major_site_id": "breast", "cached_study": {}}]
        good = {"pmid": "1", "major_outcomes": [{"major_site_id": "breast", "general_outcome_reported": True, "subcategory_outcomes": [{"subcategory_id": "breast_invasive_ductal_carcinoma", "status": "reported_separate_estimate", "evidence_text": "ductal cancer", "needs_full_text": False, "estimates": [{"context_id": "1|breast|coffee|0", "effect_size": 1.1, "lower_ci": 1.0, "upper_ci": 1.2, "effect_type": "HR", "cases": None, "sample_size": None, "comparison_type": "high vs low", "supporting_text": "HR 1.1"}]}]}]}
        self.assertEqual(enrich.validate_result(good, source, contexts), good)

    def test_current_complete_event_ignores_prompt_wording_changes(self):
        events = [{
            "pmid": "1",
            "stage": "terra",
            "source_hash": "source-v1",
            "prompt_hash": "old-prompt",
            "model": enrich.TERRA_MODEL,
            "status": "complete",
        }]
        self.assertTrue(enrich.has_current_complete_event(
            events, "1", "terra", "source-v1", enrich.TERRA_MODEL
        ))
        self.assertFalse(enrich.has_current_complete_event(
            events, "1", "terra", "source-v2", enrich.TERRA_MODEL
        ))

    def test_luna_escalation_uses_latest_terra_result_for_current_source(self):
        unclear = {
            "pmid": "1", "stage": "terra", "status": "complete",
            "source_hash": "source-v1", "created_at": "2026-01-01T00:00:00Z",
            "result": {"major_outcomes": [{"subcategory_outcomes": [{
                "status": "unclear_needs_full_text"
            }]}]},
        }
        clear = {
            **unclear,
            "created_at": "2026-01-02T00:00:00Z",
            "result": {"major_outcomes": [{"subcategory_outcomes": []}]},
        }
        with patch.object(enrich, "annotation_packet", return_value={"events": [unclear, clear]}):
            self.assertEqual(
                enrich.needs_luna_from_terra({"1": {"source_hash": "source-v1"}}),
                set(),
            )


if __name__ == "__main__":
    unittest.main()
