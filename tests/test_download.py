"""Network-free regressions for bounded downloads and same-byte inspection."""
import io
import pathlib
import sys
import unittest
import urllib.error
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import validate as v

class Response(io.BytesIO):
    pass

class DownloadTests(unittest.TestCase):
    def test_reject_redirect_before_requesting_untrusted_host(self):
        error = urllib.error.HTTPError('https://github.com/x', 302, 'redirect',
                                      {'Location':'https://localhost/private'}, None)
        with patch.object(v.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = error
            with self.assertRaisesRegex(ValueError, 'Unapproved'): v.download('https://github.com/x')
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_redirect_loop_is_bounded(self):
        error = urllib.error.HTTPError('https://github.com/x', 302, 'redirect',
                                      {'Location':'https://github.com/x'}, None)
        with patch.object(v.urllib.request, 'build_opener') as factory:
            factory.return_value.open.side_effect = error
            with self.assertRaisesRegex(ValueError, 'Too many redirects'): v.download('https://github.com/x')
            self.assertEqual(factory.return_value.open.call_count, 5)

    def test_byte_limit_without_content_length(self):
        with patch.object(v, 'LIMIT', 16), patch.object(v.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = Response(b'x' * 17)
            with self.assertRaisesRegex(ValueError, 'exceeds'): v.download('https://github.com/x')

    def test_one_download_returns_exact_bytes_without_reopening_url(self):
        with patch.object(v.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = Response(b'exact bytes')
            self.assertEqual(v.download('https://github.com/x'), b'exact bytes')
            self.assertEqual(factory.return_value.open.call_count, 1)
            request = factory.return_value.open.call_args.args[0]
            self.assertNotIn('Authorization', request.headers)

    def test_withdrawal_reason_cannot_be_rewritten(self):
        import copy
        data = v.read(v.ROOT / 'tests/fixtures/source-only.json')
        p = data['plugins'][0]
        p['current'] = None
        p['versions'][0]['withdrawal'] = {'at':'2026-10-26T06:00:00Z', 'reason':'Original reason',
                                        'advisory':'https://github.com/owner/repo/issues/1'}
        baseline = copy.deepcopy(data)
        p['versions'][0]['withdrawal']['reason'] = 'Replacement reason'
        with self.assertRaisesRegex(ValueError, 'Withdrawal'): v.validate(data, baseline)

if __name__ == '__main__': unittest.main()
