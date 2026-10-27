"""Offline small fixtures for reviewed delivery; no plugin execution or extraction."""
import copy
import io
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import build_snapshot as build
import verify_snapshot

ROOT = build.ROOT
SEED = '32578ae27ff86f0151511478d698a1cdc12fb2e0'
BOOT = ROOT/'distribution/bootstrap'


class DeliveryV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='netcatty-delivery-v2-')
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        shutil.copytree(ROOT/'schema', self.root/'schema')
        (self.root/'distribution').mkdir()
        self.pins = json.loads((ROOT/'tests/fixtures/bootstrap-sources.json').read_bytes())
        self.pins['deliveryVersion'] = 2
        pin = self.pins['plugins'][0]['resources']['iconLight']
        self.avatar = (BOOT/'assets'/f"{pin['sha256']}.png").read_bytes()
        self.pins['authors'] = [{'subject':'project:netcatty', 'displayName':'Netcatty',
            'avatar':{'source':{'kind':'repository','repository':'binaricat/Netcatty',
                              'commit':self.pins['plugins'][0]['commit'],'sourcePath':'project.png'},
                      'sha256':build.sha(self.avatar),'size':len(self.avatar),'format':'png'}}]
        for p in self.pins['plugins']:
            p['authorSubject'] = 'project:netcatty'
        self.ledger = json.loads((BOOT/'index.json').read_bytes())
        self.package = None
        self.author_calls = 0
        self.package_calls = []
        self.addCleanup(patch.stopall)
        patch.object(build, 'ROOT', self.root).start()
        patch.object(build, 'git_file', side_effect=self.registry).start()

    def registry(self, ref, name):
        self.assertEqual(ref, SEED)
        return build.canonical(self.ledger if name == 'index.json' else build.validate.validate(self.ledger))

    def source(self, repository, commit, path):
        for p in self.pins['plugins']:
            for pin in p['resources'].values():
                if (repository,commit,path) == (p['repository'],p['commit'],pin['sourcePath']):
                    return (BOOT/'assets'/f"{pin['sha256']}{pathlib.PurePosixPath(path).suffix}").read_bytes()
        self.fail('Unexpected source request')

    def avatar_source(self, source):
        self.author_calls += 1
        return self.avatar

    def package_source(self, url):
        self.package_calls.append(url)
        return self.package

    def release(self):
        plugin = self.ledger['plugins'][0]
        record = copy.deepcopy(plugin['versions'][0])
        record['distribution'] = 'release'
        record['tag'] = 'fixture-0.1.3'
        entry = record['entry']
        entry['version'] = entry['manifest']['version'] = '0.1.3'
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('netcatty.plugin.json', json.dumps(entry['manifest']))
            archive.writestr('dist/index.js', '// Static test fixture only; never executed.\n')
        self.package = stream.getvalue()
        self.assertLess(len(self.package), 8192)
        entry['artifact'] = {'url':f"https://github.com/{entry['repository']}/releases/download/{record['tag']}/fixture.ncpkg", 'sha256':build.sha(self.package)}
        plugin['versions'].append(record)
        plugin['current'] = entry['version']
        self.pins['plugins'][0]['version'] = entry['version']
        return entry

    def run_build(self, name='snapshot'):
        (self.root/'distribution/sources.json').write_bytes(build.canonical(self.pins))
        out = self.root/name
        pointer = build.build(SEED, out, fetcher=self.source,
                              package_fetcher=self.package_source, avatar_fetcher=self.avatar_source)
        verify_snapshot.verify(out, build.sha((out/'SHA256SUMS').read_bytes()), SEED)
        return out, pointer

    def test_v2_deterministic_snapshot_keeps_canonical_provenance(self):
        entry = self.release()
        original = copy.deepcopy(self.ledger)
        out, pointer = self.run_build()
        again, other = self.run_build('again')
        self.assertEqual(pointer, other)
        self.assertEqual((out/'SHA256SUMS').read_bytes(), (again/'SHA256SUMS').read_bytes())
        self.assertEqual(self.ledger, original)
        delivery = json.loads((out/'delivery.json').read_bytes())
        self.assertEqual(delivery['schemaVersion'], 2)
        self.assertEqual(self.author_calls, 2)  # one per build, shared by both authors
        ref = delivery['plugins'][0]['artifact']
        self.assertEqual(ref['size'], len(self.package))
        self.assertEqual((out/ref['path'].lstrip('/')).read_bytes(), self.package)
        catalog = json.loads((out/'catalog.json').read_bytes())
        self.assertEqual(catalog[0]['artifact']['url'], build.ORIGIN + ref['path'])
        self.assertEqual(self.package_calls, [entry['artifact']['url']]*2)
        self.assertEqual(delivery['plugins'][0]['avatar'], delivery['plugins'][1]['avatar'])

    def test_default_v1_does_not_fetch_or_publish_prepared_avatars(self):
        self.pins['deliveryVersion'] = 1
        out, _ = self.run_build()
        delivery = json.loads((out/'delivery.json').read_bytes())
        self.assertEqual(delivery['schemaVersion'], 1)
        self.assertTrue(all(p['avatar'] is None and p['artifact'] is None for p in delivery['plugins']))
        self.assertEqual(self.author_calls, 0)
        self.assertEqual(self.package_calls, [])

    def test_v1_rejects_release_before_fetch(self):
        self.release(); self.pins['deliveryVersion'] = 1
        with self.assertRaisesRegex(ValueError, 'requires reviewed deliveryVersion 2'):
            self.run_build()
        self.assertEqual(self.package_calls, [])
        self.assertFalse((self.root/'snapshot').exists())

    def test_wrong_package_hash_never_publishes_partial_snapshot(self):
        self.release(); self.package += b'changed'
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.run_build()
        self.assertFalse((self.root/'snapshot').exists())
        self.assertEqual(list(self.root.glob('.snapshot-*')), [])

    def test_reviewed_author_mapping_must_match_display_author(self):
        self.pins['authors'][0]['displayName'] = 'Another author'
        with self.assertRaisesRegex(ValueError, 'displayed author'):
            self.run_build()
        self.assertEqual(self.author_calls, 0)

    def test_github_avatar_subject_is_explicit(self):
        self.pins['authors'][0]['avatar']['source'] = {'kind':'github-avatar','userId':123}
        with self.assertRaisesRegex(ValueError, 'account does not match'):
            self.run_build()
        self.pins['authors'][0]['subject'] = 'github-user:123'
        for p in self.pins['plugins']:
            p['authorSubject'] = 'github-user:123'
        self.run_build()

    def test_avatar_hash_mismatch_fails_without_silent_fallback(self):
        self.avatar += b'changed'
        with self.assertRaisesRegex(ValueError, 'Avatar size/hash mismatch'):
            self.run_build()
        self.assertFalse((self.root/'snapshot').exists())

    def test_null_author_avatar_stays_null(self):
        self.pins['authors'][0]['avatar'] = None
        out, _ = self.run_build()
        self.assertEqual(self.author_calls, 0)
        self.assertTrue(all(p['avatar'] is None for p in json.loads((out/'delivery.json').read_bytes())['plugins']))

    def test_package_download_uses_remaining_snapshot_budget(self):
        entry = self.release()
        (self.root/'distribution/sources.json').write_bytes(build.canonical(self.pins))
        with patch.object(build, 'MAX_TOTAL', 10000), patch.object(build.validate, 'download', return_value=self.package) as download:
            build.build(SEED, self.root/'snapshot', fetcher=self.source, avatar_fetcher=self.avatar_source)
        # Starter README and two icons precede the package; avatar deduplicates
        # to the light icon. The reader receives the remaining budget up front.
        download.assert_called_once_with(entry['artifact']['url'], limit=10000-2050-873-873)

    def test_withdrawn_history_is_preserved_without_fetching_its_package(self):
        self.release()
        plugin = self.ledger['plugins'][0]
        plugin['current'] = '0.1.2'
        plugin['versions'][-1]['withdrawal'] = {'at':'2026-10-27T00:00:00Z',
            'reason':'Fixture withdrawal', 'advisory':'https://github.com/binaricat/netcatty-plugins/issues/1'}
        self.pins['plugins'][0]['version'] = '0.1.2'
        original = copy.deepcopy(self.ledger)
        out, _ = self.run_build()
        self.assertEqual(self.package_calls, [])
        self.assertEqual(self.ledger, original)
        history = json.loads((out/'index.json').read_bytes())['plugins'][0]['versions'][-1]
        self.assertEqual(history['withdrawal'], original['plugins'][0]['versions'][-1]['withdrawal'])
        self.assertTrue(history['entry']['artifact']['url'].startswith(build.ORIGIN+'/assets/'))
        self.assertEqual(list((out/'assets').glob('*.ncpkg')), [])


if __name__ == '__main__':
    unittest.main()
