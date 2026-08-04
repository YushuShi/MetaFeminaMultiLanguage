import unittest

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

    def test_summary_requires_a_disease_choice_before_showing_plots(self):
        response = self.client.get('/summary')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Choose a disease scope', response.data)
        self.assertNotIn(b'Heterogeneity diagnostics', response.data)

    def test_selected_disease_shows_all_requested_plot_groups(self):
        response = self.client.get('/summary?disease=ovarian')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Ovarian cancer', response.data)
        self.assertIn(b'All nutritional exposure evidence', response.data)
        self.assertIn(b'Dietary-intake evidence', response.data)
        self.assertIn(b"Egger&#39;s test vs heterogeneity", response.data)
        self.assertIn(b'Effect size vs heterogeneity', response.data)

    def test_summary_plot_route_rejects_unknown_paths(self):
        response = self.client.get('/summary/plots/breast/not-a-plot')

        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    unittest.main()
