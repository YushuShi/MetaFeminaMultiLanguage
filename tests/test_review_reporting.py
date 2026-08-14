import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module
from app import REPORTER_COOKIE_NAME, app, send_developer_notification


class ReviewReportingTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True

    def _client(self):
        client = app.test_client()
        client.get('/')
        return client

    def _store(self, directory):
        path = Path(directory) / 'verifications.json'
        path.write_text('{}', encoding='utf-8')
        return str(path)

    def _subcategory_study(self):
        request_payload = {
            'disease': 'Breast cancer',
            'subcategory': 'triple_negative_breast_cancer',
            'exposure': 'Alcohol',
            'outcome': 'Incidence',
        }
        response = app.test_client().post('/analyze', json=request_payload)
        self.assertEqual(response.status_code, 200)
        return request_payload, response.get_json()['studies'][0]

    def test_render_blueprint_declares_durable_review_storage_and_secrets(self):
        root = Path(__file__).resolve().parents[1]
        blueprint = (root / 'render.yaml').read_text(encoding='utf-8')
        script = (root / 'static' / 'script.js').read_text(encoding='utf-8')

        self.assertIn('mountPath: /var/data', blueprint)
        self.assertIn('value: /var/data/verifications.json', blueprint)
        self.assertIn('key: REPORTER_ID_SECRET', blueprint)
        self.assertGreaterEqual(script.count('outcome, subcategory'), 2)

    def test_missing_or_tampered_reporter_cookie_is_rejected(self):
        payload = {
            'pmid': '123', 'disease': 'Breast cancer',
            'exposure': 'Alcohol', 'outcome': 'Incidence',
        }
        missing = app.test_client().post('/exclude', json=payload)
        self.assertEqual(missing.status_code, 428)

        tampered_client = self._client()
        tampered_client.set_cookie(REPORTER_COOKIE_NAME, 'A' * 24)
        tampered = tampered_client.post('/exclude', json=payload)
        self.assertEqual(tampered.status_code, 428)

    def test_cross_site_review_request_is_rejected_without_cors(self):
        client = self._client()
        response = client.post(
            '/exclude',
            json={
                'pmid': '123', 'disease': 'Breast cancer',
                'exposure': 'Alcohol', 'outcome': 'Incidence',
            },
            headers={'Origin': 'https://malicious.example'},
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn('Access-Control-Allow-Origin', response.headers)

    def test_verify_is_idempotent_per_browser_and_persists_subcategory(self):
        request_payload, study = self._subcategory_study()
        report = {**request_payload, 'pmid': study['PMID'], 'study_data': study}
        first_client = self._client()
        second_client = self._client()

        with tempfile.TemporaryDirectory() as tempdir:
            store = self._store(tempdir)
            with (
                patch('app.VERIFICATIONS_FILE', store),
                patch('app.send_developer_notification', return_value=(True, None)) as notify,
            ):
                first = first_client.post('/verify', json=report)
                duplicate = first_client.post('/verify', json=report)
                second = second_client.post('/verify', json=report)
                refreshed = app.test_client().post('/analyze', json=request_payload)
                persisted = json.loads(Path(store).read_text(encoding='utf-8'))

        self.assertEqual(first.get_json()['count'], 1)
        self.assertEqual(duplicate.get_json()['count'], 1)
        self.assertEqual(second.get_json()['count'], 2)
        self.assertTrue(second.get_json()['notification_sent'])
        refreshed_study = next(
            row for row in refreshed.get_json()['studies']
            if str(row['PMID']) == str(study['PMID'])
        )
        self.assertEqual(refreshed_study['verifications'], 2)
        self.assertEqual(refreshed_study['verification_status'], 'review_requested')
        saved_context = next(iter(persisted[str(study['PMID'])]['contexts'].values()))
        self.assertEqual(
            saved_context['submissions'][0]['data']['Effect Size'],
            study['Effect Size'],
        )
        notify.assert_called_once()

    def test_subcategory_registry_id_and_slug_share_one_context_key(self):
        request_payload, study = self._subcategory_study()
        report = {
            **request_payload,
            'subcategory': 'breast_triple_negative_breast_cancer',
            'pmid': study['PMID'],
        }
        with tempfile.TemporaryDirectory() as tempdir:
            store = self._store(tempdir)
            with patch('app.VERIFICATIONS_FILE', store):
                response = self._client().post('/exclude', json=report)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()['context_key'],
            'breast_cancer_alcohol_incidence_triple_negative_breast_cancer',
        )

    def test_email_is_claimed_before_sending_and_not_immediately_duplicated(self):
        request_payload, study = self._subcategory_study()
        report = {**request_payload, 'pmid': study['PMID']}
        first_client = self._client()
        second_client = self._client()

        with tempfile.TemporaryDirectory() as tempdir:
            store = self._store(tempdir)
            real_save = app_module._atomic_save_verifications
            save_calls = 0

            def fail_email_result_commit(payload):
                nonlocal save_calls
                save_calls += 1
                if save_calls == 3:
                    raise OSError('disk full after SMTP')
                return real_save(payload)

            with (
                patch('app.VERIFICATIONS_FILE', store),
                patch('app._atomic_save_verifications', side_effect=fail_email_result_commit),
                patch('app.send_developer_notification', return_value=(True, None)) as notify,
            ):
                first_client.post('/exclude', json=report)
                threshold = second_client.post('/exclude', json=report)
                immediate_retry = second_client.post('/exclude', json=report)

            persisted = json.loads(Path(store).read_text(encoding='utf-8'))

        self.assertTrue(threshold.get_json()['notification_sent'])
        self.assertTrue(threshold.get_json()['notification_pending'])
        self.assertFalse(immediate_retry.get_json()['notification_sent'])
        notify.assert_called_once()
        context = next(iter(persisted[str(study['PMID'])]['contexts'].values()))
        self.assertIn(
            'pending_event_id',
            context['notifications']['exclusion_flags'],
        )

    def test_transport_details_are_not_returned_to_browser(self):
        request_payload, study = self._subcategory_study()
        report = {**request_payload, 'pmid': study['PMID']}
        with tempfile.TemporaryDirectory() as tempdir:
            store = self._store(tempdir)
            with (
                patch('app.VERIFICATIONS_FILE', store),
                patch(
                    'app.send_developer_notification',
                    return_value=(False, 'SMTP account sender@example.test rejected'),
                ),
            ):
                self._client().post('/exclude', json=report)
                response = self._client().post('/exclude', json=report)

        payload = response.get_json()
        self.assertEqual(payload['notification_error_code'], 'email_unavailable')
        self.assertNotIn('notification_error', payload)
        self.assertNotIn('sender@example.test', response.get_data(as_text=True))

    def test_corrupt_review_store_is_reported_as_unavailable(self):
        request_payload, _ = self._subcategory_study()
        with tempfile.TemporaryDirectory() as tempdir:
            store = Path(tempdir) / 'verifications.json'
            store.write_text('{bad json', encoding='utf-8')
            with patch('app.VERIFICATIONS_FILE', str(store)):
                response = app.test_client().post('/analyze', json=request_payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['review_store_available'])

    def test_smtp_partial_recipient_rejection_is_not_marked_sent(self):
        class RejectingSMTP:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def starttls(self):
                pass

            def login(self, *_args):
                pass

            def send_message(self, _message):
                return {'shiyushu2006@gmail.com': (550, b'rejected')}

        with (
            patch.dict('os.environ', {
                'SMTP_HOST': 'smtp.example.test',
                'SMTP_FROM': 'sender@example.test',
                'SMTP_USERNAME': 'sender@example.test',
                'SMTP_PASSWORD': 'password',
            }, clear=False),
            patch('app.smtplib.SMTP', RejectingSMTP),
        ):
            sent, error = send_developer_notification(
                'exclusion_flags', 'Alcohol', 'Breast cancer', 'Incidence', '123'
            )

        self.assertFalse(sent)
        self.assertIn('rejected 1 review recipient', error)


if __name__ == '__main__':
    unittest.main()
