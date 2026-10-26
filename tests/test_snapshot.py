"""Normal, offline static snapshot contract checks; no ZIP payload tests."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import build_snapshot as build

SEED = '32578ae27ff86f0151511478d698a1cdc12fb2e0'
BOOTSTRAP = build.ROOT / 'distribution/bootstrap'


class SnapshotTests(unittest.TestCase):
    def source(self, repository, commit, path):
        pins = json.loads((build.ROOT/'distribution/sources.json').read_text())
        for item in pins['plugins']:
            for pin in item['resources'].values():
                if item['repository'] == repository and item['commit'] == commit and pin['sourcePath'] == path:
                    return (BOOTSTRAP/'assets'/f"{pin['sha256']}{pathlib.PurePosixPath(path).suffix}").read_bytes()
        self.fail('Unexpected upstream resource')

    def source_registry(self, commit, path):
        self.assertEqual(commit, SEED)
        return (BOOTSTRAP/path).read_bytes()

    def test_offline_reproduction_and_bindings(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(build, 'git_file', side_effect=self.source_registry):
            output = pathlib.Path(directory)/'snapshot'
            pointer = build.build(SEED, output, fetcher=self.source)
            self.assertEqual(pointer, json.loads((BOOTSTRAP/'v1/snapshot.json').read_text()))
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
        with tempfile.TemporaryDirectory() as directory, patch.object(build, 'git_file', side_effect=self.source_registry):
            output = pathlib.Path(directory)/'snapshot'
            with self.assertRaises(OSError):
                build.build(SEED, output, fetcher=unavailable)
            self.assertFalse(output.exists())
            self.assertEqual(list(pathlib.Path(directory).iterdir()), [])

    def test_existing_snapshot_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                build.build(SEED, pathlib.Path(directory), fetcher=self.source)

    def test_bootstrap_checksums(self):
        for line in (BOOTSTRAP/'SHA256SUMS').read_text().splitlines():
            digest, path = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((BOOTSTRAP/path).read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()
