import json
import re
import unittest
from unittest.mock import patch
from pathlib import Path

from app import app


class SummaryPageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_homepage_places_summary_navigation_next_to_about(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/summary" class="header-action">Summary</a>', response.data)
        self.assertIn(b'href="/about" class="header-action header-action--primary">', response.data)
        self.assertIn(b'class="header-action-icon"', response.data)

    def test_homepage_omits_refresh_and_exclude_meta_controls(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Refresh Evidence', response.data)
        self.assertNotIn(b'Exclude Meta-Analyses', response.data)
        self.assertNotIn(b'id="refresh-btn"', response.data)
        self.assertNotIn(b'id="exclude-meta"', response.data)

    def test_homepage_groups_indented_subcategories_in_disease_scope(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'id="subcategory-group"', response.data)
        self.assertNotIn(b'id="subcategory"', response.data)
        self.assertNotIn(b'id="scope-risk"', response.data)
        self.assertIn(b'value="Breast cancer::invasive_ductal_carcinoma"', response.data)
        self.assertIn(b'data-risk="9.1"', response.data)
        self.assertIn(b'&#160;&#160;&#160;Invasive ductal carcinoma', response.data)

    def test_subcategory_lifetime_risk_is_used_only_for_sample_size_baseline(self):
        script = (Path(__file__).resolve().parents[1] / 'static' / 'script.js').read_text()

        self.assertIn('const subtypeLifetimeRisk = Number(option.dataset.risk);', script)
        self.assertIn('val = subtypeLifetimeRisk;', script)
        self.assertNotIn('estimated lifetime risk', script)

    def test_summary_requires_a_disease_choice_before_showing_plots(self):
        response = self.client.get('/summary')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Choose a disease scope', response.data)
        self.assertNotIn(b'Heterogeneity diagnostics', response.data)
        self.assertNotIn(b'Select one cancer type to view its pooled forest plots', response.data)
        self.assertNotIn(b'id="summary-subcategory"', response.data)
        self.assertIn(b'value="breast::invasive_ductal_carcinoma"', response.data)

    def test_selected_disease_shows_all_requested_plot_groups(self):
        response = self.client.get('/summary?disease=ovarian')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ovarian cancer', response.data)
        self.assertIn(b'All nutritional exposure evidence', response.data)
        self.assertIn(b'Dietary-intake evidence', response.data)
        self.assertIn(b"Egger&#39;s test vs heterogeneity", response.data)
        self.assertIn(b'Effect size vs heterogeneity', response.data)

    def test_summary_renders_a_valid_subcategory_and_its_lifetime_risk(self):
        response = self.client.get(
            '/summary?disease=breast&subcategory=breast_invasive_ductal_carcinoma'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invasive ductal carcinoma', response.data)
        self.assertIn(b'Estimated lifetime risk: 9.1%', response.data)
        self.assertIn(b'Insufficient eligible saved evidence', response.data)
        self.assertNotIn(b'Dietary-intake evidence', response.data)

    def test_summary_accepts_subcategory_from_combined_disease_scope_value(self):
        response = self.client.get(
            '/summary?disease=breast::invasive_ductal_carcinoma'
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invasive ductal carcinoma', response.data)
        self.assertIn(
            b'value="breast::invasive_ductal_carcinoma"\n                            selected',
            response.data,
        )

    def test_summary_plot_route_rejects_unknown_paths(self):
        response = self.client.get('/summary/plots/breast/not-a-plot')

        self.assertEqual(response.status_code, 404)

    def test_subcategory_summary_plot_route_uses_only_manifest_entries(self):
        manifest = {
            'scopes': {
                'breast': {
                    'subcategories': {
                        'breast_invasive_ductal_carcinoma': {
                            'plots': {
                                'forest-protective': {
                                    'path': 'Plot/forest_protective_breast.pdf',
                                    'filename': 'forest_protective_breast.pdf',
                                    'available': True,
                                }
                            }
                        }
                    }
                }
            }
        }
        with patch('app.load_json', return_value=manifest):
            allowed = self.client.get(
                '/summary/plots/breast/forest-protective?subcategory=breast_invasive_ductal_carcinoma'
            )
            rejected = self.client.get(
                '/summary/plots/breast/forest-harmful?subcategory=breast_invasive_ductal_carcinoma'
            )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(rejected.status_code, 404)
        allowed.close()
        rejected.close()

    def test_subcategory_analyze_never_falls_back_to_live_analysis(self):
        with patch('app.meta_analysis.get_analysis_data') as live_analysis:
            response = self.client.post('/analyze', json={
                'disease': 'Breast cancer',
                'subcategory': 'breast_invasive_ductal_carcinoma',
                'exposure': 'Vitamin A',
                'outcome': 'Incidence',
            })

        self.assertEqual(response.status_code, 404)
        live_analysis.assert_not_called()

    def test_subcategory_article_list_uses_saved_bibliographic_metadata(self):
        response = self.client.post('/analyze', json={
            'disease': 'Breast cancer',
            'subcategory': 'triple_negative_breast_cancer',
            'exposure': 'Alcohol',
            'outcome': 'Incidence',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        studies = payload['studies']
        self.assertGreater(len(studies), 0)
        for study in studies:
            self.assertTrue(study['Authors'])
            self.assertTrue(study['Journal'])
            self.assertTrue(study['Year'])
            self.assertRegex(
                study['Study'],
                rf'^.+(?: et al\.)? \(\d{{4}}\) \[PMID: {re.escape(str(study["PMID"]))}\]$',
            )
            self.assertNotEqual(study['Study'], study['Reference'])

        cache = json.loads((
            Path(__file__).resolve().parents[1]
            / 'Cached_results' / 'alcohol' / 'breast_cancer_incidence_true_core.json'
        ).read_text())
        main_studies = {str(study['PMID']): study for study in cache['studies']}
        for study in studies:
            main_study = main_studies[str(study['PMID'])]
            self.assertEqual(
                study['exposure_measurement_type'],
                main_study['exposure_measurement_type'],
            )
            self.assertEqual(
                study['exposure_measurement_supporting_text'],
                main_study['exposure_measurement_supporting_text'],
            )

        self.assertEqual(
            {item['omitted'] for item in payload['headline']['loo_results']},
            {study['Study'] for study in studies},
        )

    def test_requested_subcategory_plot_rules_are_encoded(self):
        root = Path(__file__).resolve().parents[1]
        analysis_source = (root / 'subcategory_analysis.py').read_text()
        paper_plot_source = (root / 'Plot' / 'PlotsPaper.R').read_text()

        self.assertNotIn("Egger's test unavailable (<10 studies)", analysis_source)
        self.assertNotIn('str(row["study"])[:28]', analysis_source)
        self.assertIn('entry["headline"].get("n_studies", 0) > 1', analysis_source)
        self.assertIn('min_studies = 2', paper_plot_source)


if __name__ == '__main__':
    unittest.main()
