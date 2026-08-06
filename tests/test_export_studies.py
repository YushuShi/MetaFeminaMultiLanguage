import json
import unittest
from pathlib import Path

from app import app


ROOT = Path(__file__).resolve().parents[1]


class ExportStudiesTests(unittest.TestCase):
    def test_export_button_is_immediately_after_select_all(self):
        html = app.test_client().get('/').get_data(as_text=True)

        select_position = html.index('id="select-all-btn"')
        export_position = html.index('id="export-studies-btn"')
        deselect_position = html.index('id="deselect-all-btn"')
        self.assertLess(select_position, export_position)
        self.assertLess(export_position, deselect_position)

    def test_csv_export_uses_displayed_studies_and_identifiers(self):
        script = (ROOT / 'static' / 'script.js').read_text(encoding='utf-8')

        self.assertIn('function exportStudiesToCsv()', script)
        self.assertIn('const rows = currentStudies.map((study, index)', script)
        self.assertIn("studyIdentifier(study, 'PMID')", script)
        self.assertIn("studyIdentifier(study, 'PMCID')", script)
        self.assertIn("new Blob([`\\uFEFF${csv}`]", script)
        self.assertIn("type: 'text/csv;charset=utf-8'", script)

    def test_export_ui_and_csv_headers_are_translated(self):
        catalog = json.loads((ROOT / 'static' / 'i18n-translations.json').read_text(encoding='utf-8'))

        for source in ('Export', 'No studies to export.', 'Row', 'Selected', 'Study',
                       'Effect Type', 'Effect Size', 'Sample Size', 'Quality Score'):
            self.assertEqual(set(catalog[source]), {'zh-CN', 'zh-TW', 'nl', 'ko'})
        self.assertEqual(catalog['Export']['zh-CN'], '导出')
        self.assertEqual(catalog['Export']['zh-TW'], '匯出')
        self.assertEqual(catalog['Export']['ko'], '내보내기')


if __name__ == '__main__':
    unittest.main()
