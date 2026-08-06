import json
import re
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import pandas as pd

from app import app
from scripts.update_plot_workbooks import filtered_result


class SummaryPageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_reanalysis_rejects_fair_studies_by_default(self):
        studies = [
            {'PMID': '1', 'Quality Score': 'Good', 'Effect Size': 1.1, 'Lower CI': 1.0, 'Upper CI': 1.2},
            {'PMID': '2', 'Quality Score': 'Moderate', 'Effect Size': 1.2, 'Lower CI': 1.0, 'Upper CI': 1.4},
            {'PMID': '3', 'Quality Score': 'Fair', 'Effect Size': 1.3, 'Lower CI': 1.0, 'Upper CI': 1.6},
        ]
        with patch('app.meta_analysis.perform_meta_analysis', return_value={'headline': {}}) as perform:
            response = self.client.post('/reanalyze', json={'studies': studies})

        self.assertEqual(response.status_code, 200)
        analyzed = perform.call_args.args[0]
        self.assertEqual(set(analyzed['PMID']), {'1', '2'})
        self.assertNotIn('Fair', set(analyzed['Quality Score']))

    def test_reanalysis_can_include_fair_studies_when_requested(self):
        studies = [
            {'PMID': '1', 'Quality Score': 'Good', 'Effect Size': 1.1, 'Lower CI': 1.0, 'Upper CI': 1.2},
            {'PMID': '2', 'Quality Score': 'Fair', 'Effect Size': 1.3, 'Lower CI': 1.0, 'Upper CI': 1.6},
        ]
        with patch('app.meta_analysis.perform_meta_analysis', return_value={'headline': {}}) as perform:
            response = self.client.post('/reanalyze', json={
                'studies': studies,
                'quality_filter': 'Fair+',
            })

        self.assertEqual(response.status_code, 200)
        analyzed = perform.call_args.args[0]
        self.assertEqual(set(analyzed['PMID']), {'1', '2'})

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

    def test_summary_plot_route_serves_localized_variant_with_english_fallback(self):
        with tempfile.TemporaryDirectory() as tempdir:
            plot_root = Path(tempdir)
            filename = 'forest_protective_breast.pdf'
            (plot_root / filename).write_bytes(b'english plot')
            localized = plot_root / 'locales' / 'zh-CN' / filename
            localized.parent.mkdir(parents=True)
            localized.write_bytes(b'localized plot')
            korean = plot_root / 'locales' / 'ko' / filename
            korean.parent.mkdir(parents=True)
            korean.write_bytes(b'korean plot')

            with patch('app.PLOT_DIR', tempdir):
                translated_response = self.client.get(
                    '/summary/plots/breast/forest-protective?lang=zh-CN'
                )
                korean_response = self.client.get(
                    '/summary/plots/breast/forest-protective?lang=ko'
                )
                missing_variant_response = self.client.get(
                    '/summary/plots/breast/forest-protective?lang=nl'
                )
                unsupported_response = self.client.get(
                    '/summary/plots/breast/forest-protective?lang=../../zh-CN'
                )

                self.assertEqual(translated_response.status_code, 200)
                self.assertEqual(translated_response.data, b'localized plot')
                self.assertEqual(korean_response.status_code, 200)
                self.assertEqual(korean_response.data, b'korean plot')
                self.assertIn('no-store', korean_response.headers['Cache-Control'])
                self.assertEqual(missing_variant_response.status_code, 200)
                self.assertEqual(missing_variant_response.data, b'english plot')
                self.assertEqual(unsupported_response.status_code, 200)
                self.assertEqual(unsupported_response.data, b'english plot')
                translated_response.close()
                korean_response.close()
                missing_variant_response.close()
                unsupported_response.close()

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

    def test_subcategory_summary_plot_route_uses_sibling_locale_variant(self):
        with tempfile.TemporaryDirectory() as tempdir:
            plot_root = Path(tempdir)
            base = (
                plot_root / 'subcategories' / 'breast'
                / 'invasive_ductal_carcinoma' / 'forest_harmful.pdf'
            )
            base.parent.mkdir(parents=True)
            base.write_bytes(b'english subtype plot')
            localized = base.parent / 'locales' / 'nl' / base.name
            localized.parent.mkdir(parents=True)
            localized.write_bytes(b'nederlandse subtype plot')
            manifest = {
                'scopes': {
                    'breast': {
                        'subcategories': {
                            'breast_invasive_ductal_carcinoma': {
                                'plots': {
                                    'forest-harmful': {
                                        'path': str(base),
                                        'filename': base.name,
                                        'available': True,
                                    }
                                }
                            }
                        }
                    }
                }
            }

            with patch('app.PLOT_DIR', tempdir), patch('app.load_json', return_value=manifest):
                response = self.client.get(
                    '/summary/plots/breast/forest-harmful'
                    '?subcategory=breast_invasive_ductal_carcinoma&lang=nl'
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, b'nederlandse subtype plot')
                response.close()

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
            self.assertEqual(study['Quality Score'], main_study['Quality Score'])
            self.assertEqual(study['JBI'], main_study['JBI'])

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
        self.assertIn('entry["headline"].get("n_studies", 0) >= 3', analysis_source)
        self.assertIn('entry["headline"]["i2"] > 0', analysis_source)
        self.assertIn('min_studies = 3', paper_plot_source)
        self.assertIn('n_studies >= min_studies', paper_plot_source)
        self.assertIn('I2 > 0', paper_plot_source)
        self.assertIn('forest_height_mm <- function(total_rows)', paper_plot_source)
        self.assertIn('height = figure_height', paper_plot_source)
        self.assertIn('figsize=(11.69, _summary_forest_height(total_rows))', analysis_source)

    def test_named_summary_rows_match_saved_study_recalculation(self):
        root = Path(__file__).resolve().parents[1]
        checks = (
            ('mushrooms', 'Breast cancer', 'breast'),
            ('glutamine', 'Breast cancer', 'breast'),
            ('calcium', 'Uterine cancer', 'uterine'),
        )

        for exposure, cancer, workbook_label in checks:
            expected = filtered_result(exposure, cancer)
            workbook = pd.read_excel(
                root / 'Plot' / f'exposures_meta_analysis_{workbook_label}_combined.xlsx'
            )
            actual = workbook.loc[workbook['Exposure'].eq(exposure)].iloc[0]
            self.assertEqual(actual['number studies'], expected['number studies'])
            self.assertAlmostEqual(actual['I^2 (%)'], expected['I^2 (%)'], places=1)
            self.assertGreater(actual['I^2 (%)'], 0)


if __name__ == '__main__':
    unittest.main()
