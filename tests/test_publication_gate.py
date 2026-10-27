"""Offline publication gate regressions; fake token, mocked network and git."""
import contextlib
import io
import json
import os
import pathlib
import sys
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import check_publication as gate

SHA = 'a' * 40
FAKE_TOKEN = 'offline-test-token-not-a-credential'


class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'GITHUB_TOKEN': FAKE_TOKEN})
        self.env.start(); self.addCleanup(self.env.stop)
        self.git = patch.object(gate.subprocess, 'check_output', return_value=SHA+'\trefs/heads/main\n')
        self.git_mock = self.git.start(); self.addCleanup(self.git.stop)
        self.network = patch.object(gate.urllib.request, 'build_opener')
        self.opener = self.network.start(); self.addCleanup(self.network.stop)
        self.response = self.opener.return_value.open.return_value.__enter__.return_value
        self.response.read.return_value = json.dumps([{'merged_at':'2026-10-27T00:00:00Z',
            'base':{'ref':'main'}, 'merge_commit_sha':SHA}]).encode()

    def test_exact_origin_token_and_no_redirect_handler(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output): gate.check(SHA)
        self.opener.assert_called_once_with(gate.NoRedirect)
        request = self.opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, f'https://api.github.com/repos/binaricat/netcatty-plugins/commits/{SHA}/pulls')
        self.assertEqual(request.get_header('Authorization'), 'Bearer '+FAKE_TOKEN)
        self.assertNotIn(FAKE_TOKEN, output.getvalue())
        self.assertNotIn('GITHUB_TOKEN', self.git_mock.call_args.kwargs['env'])
        self.assertIsNone(gate.NoRedirect().redirect_request(request, None, 302, '', {}, 'https://example.invalid/'))

    def test_missing_token_fails_without_anonymous_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'requires the workflow'): gate.check(SHA)
        self.git_mock.assert_not_called(); self.opener.assert_not_called()

    def test_stale_main_never_calls_api(self):
        self.git_mock.return_value = 'b'*40+'\trefs/heads/main\n'
        with self.assertRaisesRegex(ValueError, 'Superseded'): gate.check(SHA)
        self.opener.assert_not_called()

    def test_unmerged_or_different_commit_still_rejected(self):
        for data in [[], [{'merged_at':None,'base':{'ref':'main'},'merge_commit_sha':SHA}],
                     [{'merged_at':'now','base':{'ref':'main'},'merge_commit_sha':'b'*40}]]:
            with self.subTest(data=data):
                self.response.read.return_value=json.dumps(data).encode()
                with self.assertRaisesRegex(ValueError, 'requires a merged PR'): gate.check(SHA)

    def test_http_errors_report_only_safe_headers_without_retry(self):
        for code in [403,429,401,302]:
            with self.subTest(code=code):
                headers=Message()
                headers['Retry-After']='60'; headers['X-RateLimit-Remaining']='0'
                headers['X-RateLimit-Reset']='1793115000'; headers['X-Untrusted']=FAKE_TOKEN
                error=urllib.error.HTTPError('https://api.github.com/',code,FAKE_TOKEN,headers,io.BytesIO(FAKE_TOKEN.encode()))
                self.opener.return_value.open.reset_mock()
                self.opener.return_value.open.side_effect=error
                with self.assertRaises(ValueError) as caught: gate.check(SHA)
                text=str(caught.exception)
                self.assertNotIn(FAKE_TOKEN,text); self.assertIn('no automatic retry',text)
                self.assertEqual('Retry-After=60' in text, code in (403,429))
                self.opener.return_value.open.assert_called_once()

    def test_untrusted_rate_header_text_not_logged(self):
        headers=Message(); headers['Retry-After']=FAKE_TOKEN
        self.opener.return_value.open.side_effect=urllib.error.HTTPError('https://api.github.com/',403,'limit',headers,None)
        with self.assertRaises(ValueError) as caught: gate.check(SHA)
        self.assertNotIn(FAKE_TOKEN,str(caught.exception))

    def test_workflow_uses_existing_token_with_only_read_permissions(self):
        workflow=(pathlib.Path(__file__).resolve().parents[1]/'.github/workflows/static-snapshot.yml').read_text()
        self.assertEqual(workflow.count('    permissions:\n      contents: read\n      pull-requests: read\n'), 2)
        self.assertEqual(workflow.count('GITHUB_TOKEN: ${{ github.token }}'),5)
        self.assertEqual(workflow.count('python scripts/check_publication.py'),5)
        self.assertNotIn('pull_request_target',workflow)
        self.assertNotIn(': write',workflow)


if __name__ == '__main__': unittest.main()
