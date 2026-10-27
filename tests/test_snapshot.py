"""Normal, offline static snapshot contract checks; no ZIP payload tests."""
import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import build_snapshot as build

SEED = '32578ae27ff86f0151511478d698a1cdc12fb2e0'
BOOTSTRAP = build.ROOT / 'distribution/bootstrap'
SCHEMA = build.ROOT / 'schema'
BOOTSTRAP_PINS = pathlib.Path(__file__).parent / 'fixtures/bootstrap-sources.json'


class SnapshotTests(unittest.TestCase):
    @contextmanager
    def source_pins(self, pins_bytes=None):
        """Isolate fixture inputs without changing the production builder's loader."""
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'distribution').mkdir()
            (root/'distribution/sources.json').write_bytes(
                BOOTSTRAP_PINS.read_bytes() if pins_bytes is None else pins_bytes)
            shutil.copytree(SCHEMA, root/'schema')
            with patch.object(build, 'ROOT', root):
                yield root

    def source(self, repository, commit, path):
        pins = json.loads(BOOTSTRAP_PINS.read_bytes())
        for item in pins['plugins']:
            for pin in item['resources'].values():
                if item['repository'] == repository and item['commit'] == commit and pin['sourcePath'] == path:
                    return (BOOTSTRAP/'assets'/f"{pin['sha256']}{pathlib.PurePosixPath(path).suffix}").read_bytes()
        self.fail('Unexpected upstream resource')

    def source_registry(self, commit, path):
        self.assertEqual(commit, SEED)
        return (BOOTSTRAP/path).read_bytes()

    def test_offline_reproduction_and_bindings(self):
        with self.source_pins(), tempfile.TemporaryDirectory() as directory, patch.object(build, 'git_file', side_effect=self.source_registry):
            output = pathlib.Path(directory)/'snapshot'
            pointer = build.build(SEED, output, fetcher=self.source)
            # The historical inputs remain frozen, while builderSha256 reflects
            # the actual reviewed builder. Changing code changes snapshotId.
            historical = json.loads((BOOTSTRAP/'delivery.json').read_text())
            rebuilt = json.loads((output/'delivery.json').read_text())
            self.assertEqual(rebuilt['builderSha256'], hashlib.sha256(pathlib.Path(build.__file__).read_bytes()).hexdigest())
            self.assertEqual({k:v for k,v in rebuilt.items() if k != 'builderSha256'},
                             {k:v for k,v in historical.items() if k != 'builderSha256'})
            for name in ('catalog','index','delivery'):
                descriptor = pointer[name]
                content = (output/descriptor['path'].lstrip('/')).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), descriptor['sha256'])
                self.assertEqual(len(content), descriptor['size'])
            delivery = json.loads((output/'delivery.json').read_text())
            self.assertEqual(delivery['registryCommit'], SEED)
            self.assertEqual(len(delivery['plugins']), 2)
            for plugin in delivery['plugins']:
                self.assertIsNone(plugin['artifact'])
                self.assertIsNone(plugin['avatar'])
                for kind in ('readme','iconLight','iconDark'):
                    resource = plugin[kind]
                    if resource:
                        content = (output/resource['path'].lstrip('/')).read_bytes()
                        self.assertEqual(hashlib.sha256(content).hexdigest(), resource['sha256'])
            self.assertIn('max-age=60, must-revalidate', (output/'_headers').read_text())
            self.assertIn('max-age=31536000, immutable', (output/'_headers').read_text())

    def test_fetch_failure_leaves_no_partial_output(self):
        def unavailable(*args):
            raise OSError('upstream unavailable')
        with self.source_pins(), tempfile.TemporaryDirectory() as directory, patch.object(build, 'git_file', side_effect=self.source_registry):
            output = pathlib.Path(directory)/'snapshot'
            with self.assertRaises(OSError):
                build.build(SEED, output, fetcher=unavailable)
            self.assertFalse(output.exists())
            self.assertEqual(list(pathlib.Path(directory).iterdir()), [])

    def test_existing_snapshot_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                build.build(SEED, pathlib.Path(directory), fetcher=self.source)

    def test_live_withdrawal_keeps_history_reproducible_and_current_pins_strict(self):
        ledger = json.loads((BOOTSTRAP/'index.json').read_bytes())
        withdrawn = ledger['plugins'][-1]
        withdrawn['current'] = None
        withdrawn['versions'][0]['withdrawal'] = {
            'at': '2026-10-27T00:00:00Z', 'reason': 'Maintainer withdrawal',
            'advisory': 'https://github.com/binaricat/netcatty-plugins/issues/1'}
        catalog = build.validate.validate(ledger)
        pins = json.loads(BOOTSTRAP_PINS.read_bytes())
        pins['plugins'] = [p for p in pins['plugins'] if p['id'] != withdrawn['id']]
        current = {'index.json': build.canonical(ledger), 'catalog.json': build.canonical(catalog)}
        with self.source_pins(build.canonical(pins)) as live_root:
            # Reproduction must not read the changed live pins or current catalog.
            with patch.object(build, 'git_file', side_effect=lambda ref, path: current[path]):
                self.test_offline_reproduction_and_bindings()
                with tempfile.TemporaryDirectory() as directory:
                    output = pathlib.Path(directory)/'current'
                    build.build(SEED, output, fetcher=self.source)
                    self.assertEqual(len(json.loads((output/'delivery.json').read_bytes())['plugins']), 1)
                # An obsolete extra pin must still block actual current publication.
                (live_root/'distribution/sources.json').write_bytes(BOOTSTRAP_PINS.read_bytes())
                with tempfile.TemporaryDirectory() as directory:
                    output = pathlib.Path(directory)/'mismatched'
                    with self.assertRaisesRegex(ValueError, 'exactly cover current catalog'):
                        build.build(SEED, output, fetcher=self.source)
                    self.assertFalse(output.exists())

    def test_bootstrap_checksums(self):
        delivery = json.loads((BOOTSTRAP/'delivery.json').read_bytes())
        self.assertEqual(hashlib.sha256(BOOTSTRAP_PINS.read_bytes()).hexdigest(), delivery['sourceLockSha256'])
        for line in (BOOTSTRAP/'SHA256SUMS').read_text().splitlines():
            digest, path = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((BOOTSTRAP/path).read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
