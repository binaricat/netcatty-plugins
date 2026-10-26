import copy
import hashlib
import io
import json
import pathlib
import sys
import unittest
import zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import validate as v

class IndexTests(unittest.TestCase):
    def setUp(self):
        self.data = v.read(v.ROOT / 'tests/fixtures/source-only.json')
        self.base = copy.deepcopy(self.data)
        self.plugin = self.data['plugins'][0]
        self.record = self.plugin['versions'][0]
        self.entry = self.record['entry']

    def reject(self):
        with self.assertRaises(Exception): v.validate(self.data, self.base)

    def test_seed_and_projection(self):
        self.assertEqual(v.validate(self.data), [p['versions'][0]['entry'] for p in self.data['plugins']])
        self.assertEqual(v.validate(v.read(v.ROOT / 'index.json')), v.read(v.ROOT / 'catalog.json'))
    def test_duplicate_id(self):
        self.data['plugins'].append(copy.deepcopy(self.plugin)); self.reject()
    def test_duplicate_version(self):
        self.plugin['versions'].append(copy.deepcopy(self.record)); self.reject()
    def test_mutated_source(self):
        self.entry['commit'] = 'a'*40; self.reject()
    def test_removed_history(self):
        self.data['plugins'].pop(); self.reject()
    def test_bad_pin(self):
        self.entry['commit'] = 'main'; self.reject()
    def test_identity(self):
        self.entry['manifest']['version'] = '8.0.0'; self.reject()
    def test_license(self):
        self.entry['license'] = 'MIT'; self.reject()
    def test_paths(self):
        for path in ('../README.md','/README.md','a/%2e%2e/README.md','a\\README.md'):
            self.entry['readme'] = path; self.reject()
    def test_node(self):
        self.entry['manifest']['main']['node'] = 'index.js'; self.reject()
    def test_missing_compatibility(self):
        del self.entry['manifest']['engines']; self.reject()
    def test_unknown_field(self):
        self.entry['verifiedSafe'] = True; self.reject()
    def test_missing_current(self):
        self.plugin['current'] = '99.0.0'; self.reject()
    def test_withdrawal(self):
        self.record['withdrawal'] = {'at':'2026-10-26T06:00:00Z','reason':'Maintainer withdrawal','advisory':'https://github.com/binaricat/netcatty-plugins/issues/1'}
        self.reject()
        self.plugin['current'] = None
        self.assertEqual(len(v.validate(self.data, self.base)), 1)
        baseline = copy.deepcopy(self.data)
        self.record['withdrawal'] = None
        with self.assertRaises(ValueError): v.validate(self.data, baseline)
    def release(self):
        self.record['distribution'] = 'release'; self.record['tag'] = 'starter-v0.1.2'
        self.entry['artifact'] = {'url':'https://github.com/binaricat/Netcatty/releases/download/starter-v0.1.2/starter-0.1.2.ncpkg','sha256':'a'*64}
    def test_release_requires_hash_and_tag(self):
        self.release(); v.validate(self.data)
        del self.entry['artifact']['sha256']
        with self.assertRaises(Exception): v.validate(self.data)
    def test_source_only_upgrade_is_immutable(self):
        self.release(); self.reject()
    def test_hash_replacement(self):
        self.release(); baseline = copy.deepcopy(self.data)
        self.entry['artifact']['sha256'] = 'b'*64
        with self.assertRaises(ValueError): v.validate(self.data, baseline)
    def test_bad_release_url(self):
        self.release(); self.entry['artifact']['url'] = 'https://github.com/other/repo/releases/download/v1/a.ncpkg'
        with self.assertRaises(ValueError): v.validate(self.data)
    def test_new_version_cannot_reuse_tag(self):
        self.release(); record = copy.deepcopy(self.record)
        record['entry']['version'] = record['entry']['manifest']['version'] = '0.1.3'
        self.plugin['versions'].append(record)
        with self.assertRaises(ValueError): v.validate(self.data)
    def test_source_only_has_no_package(self):
        self.entry['artifact'] = {'url':'https://github.com/x/y/a.ncpkg','sha256':'a'*64}; self.reject()
    def test_url_policy(self):
        for url in ('http://github.com/x','https://github.com.evil.test/a','https://user:pass@github.com/a','https://localhost/a','https://github.com:443/a'):
            with self.assertRaises(ValueError): v.url_allowed(url)
    def test_package_inspection(self):
        self.release()
        def archive(manifest, extra=None):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as z:
                z.writestr('netcatty.plugin.json', json.dumps(manifest))
                if extra: z.writestr(extra, 'never executed')
            content = stream.getvalue()
            self.entry['artifact']['sha256'] = hashlib.sha256(content).hexdigest()
            return content
        v.inspect_package(archive(self.entry['manifest'], 'dist/index.js'), self.entry)
        with self.assertRaises(ValueError): v.inspect_package(archive({}, 'dist/index.js'), self.entry)
        with self.assertRaises(ValueError): v.inspect_package(archive(self.entry['manifest'], '../escape'), self.entry)
        content = archive(self.entry['manifest']); self.entry['artifact']['sha256'] = 'a'*64
        with self.assertRaises(ValueError): v.inspect_package(content, self.entry)
    def test_duplicate_json_keys(self):
        with self.assertRaises(ValueError): json.loads('{"x":1,"x":2}', object_pairs_hook=v.pairs)

if __name__ == '__main__': unittest.main()
