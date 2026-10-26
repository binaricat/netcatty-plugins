"""Synthetic ZIP/JSON regressions; no plugin code is loaded or executed."""
import copy
import hashlib
import io
import json
import pathlib
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import validate as v


def make_archive(data, method=zipfile.ZIP_DEFLATED, declared_prefix=None, descriptor=False):
    class Unseekable(io.BytesIO):
        def seek(self, *args):
            raise io.UnsupportedOperation('not seekable')
    stream = Unseekable() if descriptor else io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=method) as archive:
        archive.writestr('netcatty.plugin.json', data)
    content = bytearray(stream.getvalue())
    if declared_prefix is not None:
        # Both directories falsely declare only the valid JSON prefix. The full
        # DEFLATE payload still expands to JSON plus attacker-controlled bytes.
        central = content.index(b'PK\x01\x02')
        crc = zlib.crc32(declared_prefix)
        struct.pack_into('<I', content, central + 16, crc)
        struct.pack_into('<I', content, central + 24, len(declared_prefix))
        if not descriptor:
            struct.pack_into('<I', content, 14, crc)
            struct.pack_into('<I', content, 22, len(declared_prefix))
    return bytes(content)


class AdversarialPackageTests(unittest.TestCase):
    def setUp(self):
        self.data = v.read(v.ROOT / 'tests/fixtures/source-only.json')
        self.entry = self.data['plugins'][0]['versions'][0]['entry']
        self.manifest = json.dumps(self.entry['manifest']).encode()

    def inspect(self, content):
        self.entry['artifact'] = {'sha256': hashlib.sha256(content).hexdigest()}
        return v.inspect_package(content, self.entry)

    def test_manifest_output_exceeds_limit_despite_small_directory_size(self):
        content = make_archive(self.manifest + b' ' * (2 * 1024 * 1024), declared_prefix=self.manifest)
        self.assertLess(len(content), 4096)
        with self.assertRaisesRegex(ValueError, 'actual size exceeds'):
            self.inspect(content)

    def test_short_hidden_output_is_rejected_even_below_limit(self):
        content = make_archive(self.manifest + b' hidden output', declared_prefix=self.manifest)
        with self.assertRaisesRegex(ValueError, 'actual/declared size mismatch'):
            self.inspect(content)

    def test_deflate_output_call_is_bounded_independent_of_declared_size(self):
        content = make_archive(self.manifest + b' ' * (2 * 1024 * 1024), declared_prefix=self.manifest)
        decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        with patch.object(v.zlib, 'decompressobj') as factory:
            proxy = factory.return_value
            proxy.decompress.side_effect = decoder.decompress
            with self.assertRaisesRegex(ValueError, 'actual size exceeds'):
                self.inspect(content)
            self.assertEqual(proxy.decompress.call_args.args[1], v.MANIFEST_LIMIT + 1)

    def test_valid_stored_deflated_and_data_descriptor_archives(self):
        for method, descriptor in ((zipfile.ZIP_STORED, False), (zipfile.ZIP_DEFLATED, False),
                                   (zipfile.ZIP_DEFLATED, True)):
            with self.subTest(method=method, descriptor=descriptor):
                self.inspect(make_archive(self.manifest, method=method, descriptor=descriptor))

    def test_data_descriptor_does_not_bypass_actual_size_check(self):
        content = make_archive(self.manifest + b' ' * (2 * 1024 * 1024), declared_prefix=self.manifest, descriptor=True)
        with self.assertRaisesRegex(ValueError, 'actual size exceeds'):
            self.inspect(content)

    def test_crc_mismatch(self):
        content = bytearray(make_archive(self.manifest))
        central = content.index(b'PK\x01\x02')
        struct.pack_into('<I', content, 14, 0)
        struct.pack_into('<I', content, central + 16, 0)
        with self.assertRaisesRegex(ValueError, 'CRC mismatch'):
            self.inspect(bytes(content))

    def test_local_header_disagreement(self):
        content = bytearray(make_archive(self.manifest))
        struct.pack_into('<I', content, 22, 1)
        with self.assertRaisesRegex(ValueError, 'Local/central'):
            self.inspect(bytes(content))

    def test_boolean_manifest_version_not_equal_to_integer(self):
        manifest = copy.deepcopy(self.entry['manifest'])
        manifest['manifestVersion'] = True
        with self.assertRaisesRegex(ValueError, 'manifest differs'):
            self.inspect(make_archive(json.dumps(manifest).encode()))

    def test_boolean_nested_setting_not_equal_to_number(self):
        self.entry['manifest']['contributes']['settings'][0]['default'] = 1
        manifest = copy.deepcopy(self.entry['manifest'])
        manifest['contributes']['settings'][0]['default'] = True
        with self.assertRaisesRegex(ValueError, 'manifest differs'):
            self.inspect(make_archive(json.dumps(manifest).encode()))

    def test_boolean_catalog_rejected_with_valid_index_and_baseline(self):
        catalog = v.validate(self.data)
        catalog[0]['manifest']['manifestVersion'] = True
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for name, data in (('index.json', self.data), ('baseline.json', self.data), ('catalog.json', catalog)):
                (root / name).write_text(json.dumps(data))
            with patch.object(sys, 'argv', ['validate.py', '--root', str(root), '--baseline', str(root/'baseline.json'), '--download']):
                with self.assertRaisesRegex(ValueError, 'catalog.json must exactly match'):
                    v.main()

    def test_boolean_to_number_cannot_mutate_version_history(self):
        manifest = self.data['plugins'][0]['versions'][0]['entry']['manifest']
        manifest['contributes']['settings'][0]['default'] = True
        baseline = copy.deepcopy(self.data)
        manifest['contributes']['settings'][0]['default'] = 1
        # Both values fit the public JSON-value schema, but cannot replace one another.
        v.validate(self.data)
        with self.assertRaisesRegex(ValueError, 'immutable'):
            v.validate(self.data, baseline)

    def test_index_and_catalog_read_reject_non_finite_json(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            with self.subTest(token=token), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                data = copy.deepcopy(self.data)
                plugin = data['plugins'][0]
                record = copy.deepcopy(plugin['versions'][0])
                record['entry']['version'] = record['entry']['manifest']['version'] = '0.1.3'
                record['entry']['manifest']['contributes']['settings'][0]['default'] = 'NON_FINITE_PLACEHOLDER'
                plugin['versions'].append(record)
                plugin['current'] = '0.1.3'
                catalog = [record['entry'], data['plugins'][1]['versions'][0]['entry']]
                for name, value in (('index.json', data), ('catalog.json', catalog)):
                    text = json.dumps(value).replace('"NON_FINITE_PLACEHOLDER"', token)
                    path = root / name
                    path.write_text(text)
                    with self.assertRaisesRegex(ValueError, 'Non-finite JSON'):
                        v.read(path)
                (root / 'baseline.json').write_text(json.dumps(self.data))
                with patch.object(sys, 'argv', ['validate.py', '--root', str(root), '--baseline', str(root/'baseline.json'), '--download']):
                    with self.assertRaisesRegex(ValueError, 'Non-finite JSON'):
                        v.main()

    def test_package_rejects_non_finite_json(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            with self.subTest(token=token):
                manifest = copy.deepcopy(self.entry['manifest'])
                manifest['contributes']['settings'][0]['default'] = 'NON_FINITE_PLACEHOLDER'
                payload = json.dumps(manifest).replace('"NON_FINITE_PLACEHOLDER"', token).encode()
                with self.assertRaisesRegex(ValueError, 'Non-finite JSON'):
                    self.inspect(make_archive(payload))

    def test_json_equality_ignores_key_order_but_preserves_types(self):
        self.assertTrue(v.json_equal({'a': [1, True], 'b': None}, {'b': None, 'a': [1, True]}))
        for left, right in ((True, 1), (False, 0), ([True], [1]), ({'a': False}, {'a': 0})):
            self.assertFalse(v.json_equal(left, right))
