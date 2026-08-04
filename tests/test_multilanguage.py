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
            self.assertEqual(set(translations), {'zh-CN', 'zh-TW', 'nl'}, source)
            self.assertTrue(all(value.strip() for value in translations.values()), source)
            if 'MetaFemina' in source:
                self.assertTrue(all('MetaFemina' in value for value in translations.values()), source)
            for token in ('RR', 'OR', 'HR', 'ARR', 'CI', 'PI', 'I²', 'τ²', 'JBI', 'LLM', 'PubMed'):
                if re.search(rf'(?<![A-Za-z]){re.escape(token)}(?![A-Za-z])', source):
                    self.assertTrue(
                        all(token in value for value in translations.values()),
                        f'{source}: {token}',
                    )

    def test_dynamic_metadata_is_explicitly_excluded_from_translation(self):
        script = (ROOT / 'static' / 'script.js').read_text()

        self.assertIn('class="notranslate" translate="no"', script)
        self.assertRegex(script, r'class="notranslate" translate="no"[^>]*>\$\{study\.Journal')
        self.assertRegex(script, r'class="notranslate" translate="no"[^>]*>\$\{study\.Year')
        self.assertRegex(script, r'class="notranslate" translate="no"[^>]*>\$\{study\.Reference')
        self.assertIn('${study.exposure_measurement_supporting_text}', script)
        self.assertIn('class="notranslate" translate="no">"${study.exposure_measurement_supporting_text}"', script)

    def test_brand_name_and_language_choice_persist(self):
        engine = (ROOT / 'static' / 'i18n.js').read_text()
        index = (ROOT / 'templates' / 'index.html').read_text()

        self.assertIn('<div class="logo">MetaFemina</div>', index)
        self.assertIn("const STORAGE_KEY = 'metafemina.language';", engine)
        self.assertIn("window.localStorage.setItem(STORAGE_KEY, locale)", engine)
        self.assertIn("window.localStorage.getItem(STORAGE_KEY)", engine)


if __name__ == '__main__':
    unittest.main()
