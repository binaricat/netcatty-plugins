"""Small admission checks: <=8 KiB archives, <=2 KiB output, no extraction/network."""
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import validate as v


class BoundedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='netcatty-bounded-admission-')
        self.addCleanup(self.directory.cleanup)
        self.entry = copy.deepcopy(v.read(v.ROOT / 'catalog.json')[0])
        self.manifest = (json.dumps(self.entry['manifest']) + '\n').encode()
        self.assertLessEqual(len(self.manifest), 2048)

    def archive(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('netcatty.plugin.json', self.manifest)
        content = bytearray(stream.getvalue())
        self.assertLessEqual(len(content), 8192)
        return content

    def inspect(self, content):
        self.assertLessEqual(len(content), 8192)
        self.entry['artifact'] = {'sha256': hashlib.sha256(content).hexdigest()}
        v.inspect_package(content, self.entry)

    def test_small_exact_json_types(self):
        for left, right in ((True, 1), (False, 0), ([True], [1]), ({'a': False}, {'a': 0})):
            self.assertLessEqual(len(json.dumps([left, right])), 4096)
            self.assertFalse(v.json_equal(left, right))

    def test_small_nonfinite_json_rejected(self):
        for token in ('NaN', 'Infinity', '-Infinity', '1e999'):
            payload = '{"value":' + token + '}'
            self.assertLessEqual(len(payload), 64)
            path = pathlib.Path(self.directory.name) / 'input.json'
            path.write_text(payload)
            with self.assertRaisesRegex(ValueError, 'Non-finite JSON'):
                v.read(path)

    def test_small_local_size_disagreement(self):
        content = self.archive()
        # Only the local uncompressed-size field changes; output remains <=2 KiB.
        struct.pack_into('<I', content, 22, len(self.manifest) - 1)
        with self.assertRaisesRegex(ValueError, 'Local/central ZIP sizes or CRC mismatch'):
            self.inspect(bytes(content))

    def test_small_stored_manifest_crc_mismatch(self):
        content = self.archive()
        name_size, extra_size = struct.unpack_from('<HH', content, 26)
        last = 30 + name_size + extra_size + len(self.manifest) - 1
        self.assertEqual(content[last], ord('\n'))
        content[last] = ord(' ')  # One payload byte; still JSON, same actual size.
        with self.assertRaisesRegex(ValueError, 'Manifest CRC mismatch'):
            self.inspect(bytes(content))


if __name__ == '__main__':
    unittest.main()
