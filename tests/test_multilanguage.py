import json
import re
import unittest
from pathlib import Path

from app import app


ROOT = Path(__file__).resolve().parents[1]


class MultiLanguagePageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_language_icon_is_immediately_before_summary_navigation(self):
        for url in ('/', '/summary'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            picker_position = html.index('data-language-picker')
            summary_position = html.index('href="/summary"', picker_position)
            about_position = html.index('href="/about"', summary_position)
            self.assertLess(picker_position, summary_position)
            self.assertLess(summary_position, about_position)

    def test_picker_offers_requested_languages_and_english_reset(self):
        response = self.client.get('/')
        html = response.get_data(as_text=True)

        self.assertIn('data-language="zh-CN"', html)
        self.assertIn('data-language="zh-TW"', html)
        self.assertIn('data-language="nl"', html)
        self.assertIn('data-language="ko"', html)
        self.assertIn('data-language="en"', html)
        self.assertIn('aria-label="Choose language"', html)

    def test_language_picker_and_engine_are_available_on_all_pages(self):
        for url in ('/', '/summary', '/about'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'data-language-picker', response.data)
            self.assertIn(b'i18n.js', response.data)

    def test_translation_catalog_is_complete_and_preserves_scientific_tokens(self):
        catalog = json.loads((ROOT / 'static' / 'i18n-translations.json').read_text())
        self.assertGreaterEqual(len(catalog), 200)

        for source, translations in catalog.items():
            self.assertEqual(set(translations), {'zh-CN', 'zh-TW', 'nl', 'ko'}, source)
            self.assertTrue(all(value.strip() for value in translations.values()), source)
            if 'MetaFemina' in source:
                self.assertTrue(all('MetaFemina' in value for value in translations.values()), source)
            for token in ('RR', 'OR', 'HR', 'ARR', 'CI', 'PI', 'I²', 'τ²', 'JBI', 'LLM', 'PubMed'):
                if re.search(rf'(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])', source):
                    self.assertTrue(
                        all(token in value for value in translations.values()),
                        f'{source}: {token}',
                    )

    def test_selector_options_and_requested_chinese_terms_are_translated(self):
        catalog = json.loads((ROOT / 'static' / 'i18n-translations.json').read_text())
        exposures = json.loads((ROOT / 'static' / 'exposures.json').read_text())

        self.assertEqual(len(exposures), 226)
        self.assertFalse([exposure for exposure in exposures if exposure not in catalog])
        self.assertEqual(catalog['Nutritional Exposure']['zh-CN'], '营养因子')
        self.assertEqual(catalog['Nutritional Exposure']['zh-TW'], '營養因子')
        self.assertEqual(catalog['Meta-Analysis']['zh-CN'], '荟萃分析')
        self.assertEqual(catalog['Meta-Analysis']['zh-TW'], '薈萃分析')
        self.assertEqual(catalog['Quality']['zh-CN'], '文章质量')
        self.assertEqual(catalog['Quality']['zh-TW'], '文章品質')

        translated_text = ' '.join(
            translation
            for translations in catalog.values()
            for locale, translation in translations.items()
            if locale in {'zh-CN', 'zh-TW'}
        )
        self.assertNotIn('营养暴露因素', translated_text)
        self.assertNotIn('營養暴露因素', translated_text)
        self.assertNotIn('營養暴露因子', translated_text)

        expected_disease_options = {
            'Breast cancer', 'Ovarian cancer', 'Uterine cancer',
            'Invasive ductal carcinoma', 'Invasive lobular carcinoma',
            'Ductal carcinoma in situ', 'Triple-negative breast cancer',
            'Inflammatory breast cancer', 'Endometrioid carcinoma',
            'Uterine serous carcinoma', 'Clear cell carcinoma',
            'Uterine carcinosarcoma', 'Uterine leiomyosarcoma',
            'High-grade serous carcinoma', 'Low-grade serous carcinoma',
            'Mucinous carcinoma', 'Ovarian germ cell tumor',
            'Sex cord-stromal tumor',
        }
        self.assertFalse(expected_disease_options - catalog.keys())

    def test_localized_exposure_display_keeps_canonical_analysis_value(self):
        script = (ROOT / 'static' / 'script.js').read_text()

        self.assertIn('function selectedExposureValue()', script)
        self.assertIn('elements.exposure.dataset.canonicalExposure = canonical;', script)
        self.assertIn('elements.exposure.value = uiText(canonical);', script)
        self.assertIn('const exposure = selectedExposureValue();', script)
        self.assertNotIn('const exposure = elements.exposure.value;', script)

    def test_summary_plot_urls_follow_the_selected_language(self):
        engine = (ROOT / 'static' / 'i18n.js').read_text()
        summary_template = (ROOT / 'templates' / 'summary.html').read_text()

        self.assertIn("url.searchParams.set('lang', locale)", engine)
        self.assertIn("url.searchParams.delete('lang')", engine)
        self.assertIn("url.searchParams.set('plot_reload'", engine)
        self.assertIn('const replacement = element.cloneNode(true);', engine)
        self.assertIn('element.replaceWith(replacement);', engine)
        self.assertIn("'ko'", engine)
        self.assertGreaterEqual(summary_template.count('data-localized-plot'), 15)

    def test_dynamic_metadata_is_explicitly_excluded_from_translation(self):
        script = (ROOT / 'static' / 'script.js').read_text()

        self.assertIn('class="notranslate" translate="no"', script)
        self.assertRegex(script, r'class="notranslate" translate="no"[^>]*>\$\{study\.Journal')
        self.assertRegex(script, r'class="notranslate" translate="no"[^>]*>\$\{study\.Year')
        self.assertRegex(script, r'class="notranslate" translate="no"[^>]*>\$\{study\.Reference')
        self.assertIn('${study.exposure_measurement_supporting_text}', script)
        self.assertIn('class="notranslate" translate="no">"${study.exposure_measurement_supporting_text}"', script)

    def test_dynamic_statistical_interpretations_are_localized_and_rerendered(self):
        script = (ROOT / 'static' / 'script.js').read_text()

        self.assertIn('function renderHeadlineInterpretation(measure, es, low, upp)', script)
        self.assertIn('function renderResultsInterpretation(measure, es, low, upp)', script)
        self.assertIn('function renderFunnelInterpretation()', script)
        self.assertIn("uiText('Statistically significant ({direction})'", script)
        self.assertIn('I² = {i2}%', script)
        self.assertIn("Egger's test indicates no significant funnel plot asymmetry", script)
        self.assertIn("The significant funnel plot asymmetry (Egger's p={p})", script)
        self.assertIn('if (lastHeadlineData) applyResultMeasureTransformation();', script)
        self.assertIn('lastAnalysisContext ? lastAnalysisContext.exposure', script)
        self.assertIn('lastAnalysisContext ? lastAnalysisContext.disease', script)
        self.assertIn('updateResultsUI(data, { disease, exposure });', script)

        self.assertNotIn("elements.interpretation.classList.add('notranslate')", script)
        self.assertNotIn("elements.funnelInterpretation.classList.add('notranslate')", script)
        self.assertNotIn("elements.resultsInterpretation.classList.add('notranslate')", script)
        self.assertNotIn("elements.interpretation.setAttribute('translate', 'no')", script)
        self.assertNotIn("elements.funnelInterpretation.setAttribute('translate', 'no')", script)
        self.assertNotIn("elements.resultsInterpretation.setAttribute('translate', 'no')", script)

    def test_brand_name_and_language_choice_persist(self):
        engine = (ROOT / 'static' / 'i18n.js').read_text()
        index = (ROOT / 'templates' / 'index.html').read_text()

        self.assertIn('<div class="logo">MetaFemina</div>', index)
        self.assertIn("const STORAGE_KEY = 'metafemina.language';", engine)
        self.assertIn("window.localStorage.setItem(STORAGE_KEY, locale)", engine)
        self.assertIn("window.localStorage.getItem(STORAGE_KEY)", engine)


if __name__ == '__main__':
    unittest.main()
