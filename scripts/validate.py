"""Static index admission. Never import, extract, build or execute a plugin."""
import argparse
import copy
import hashlib
import io
import json
import math
import pathlib
import re
import struct
import urllib.parse
import urllib.request
import zipfile
import zlib
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = pathlib.Path(__file__).resolve().parents[1]
LIMIT = 32 * 1024 * 1024
MANIFEST_LIMIT = 1024 * 1024
HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}

def require(ok, message):
    if not ok:
        raise ValueError(message)

def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result

def json_equal(left, right):
    """JSON comparison that never treats booleans as numbers (Python does)."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(value, right[key]) for key, value in left.items())
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return left == right

def reject_constant(value):
    raise ValueError('Non-finite JSON number: ' + value)

def json_float(value):
    number = float(value)
    require(math.isfinite(number), 'Non-finite JSON number')
    return number

def load_json(content):
    return json.loads(content, object_pairs_hook=pairs,
                      parse_constant=reject_constant, parse_float=json_float)

def read(path):
    require(not path.is_symlink(), 'Symlinks are forbidden')
    require(path.stat().st_size <= 8 * 1024 * 1024, 'JSON exceeds 8 MiB')
    return load_json(path.read_text())

def url_allowed(url):
    u = urllib.parse.urlsplit(url)
    require(u.scheme == 'https' and u.hostname in HOSTS and not u.username and not u.password
            and not u.port and not u.fragment, 'Unapproved download URL')
    return url

def validate(data, baseline=None):
    contract = read(ROOT / 'schema/plugin-contract.schema.json')
    registry = Registry().with_resource(contract['$id'], Resource.from_contents(contract))
    Draft202012Validator(read(ROOT / 'schema/index.schema.json'), registry=registry,
                        format_checker=FormatChecker()).validate(data)
    ids, catalog = set(), []
    for plugin in data['plugins']:
        require(plugin['id'] not in ids, 'Duplicate plugin ID')
        ids.add(plugin['id'])
        versions, tags, urls, hashes = set(), set(), set(), set()
        for record in plugin['versions']:
            e = record['entry']; m = e['manifest']; v = e['version']
            require(e['id'] == plugin['id'] == m['id'] and v == m['version'], 'Identity/version mismatch')
            require(v not in versions, 'Duplicate version')
            versions.add(v)
            require(m.get('license') == e['license'], 'License mismatch')
            p = e['readme']
            require(p.endswith('.md') and not re.search(r'[\\%?#\x00]', p)
                    and all(x not in ('', '.', '..') for x in p.split('/')), 'Unsafe README path')
            main = m.get('main', {})
            perms = [x if isinstance(x, str) else x['permission'] for x in
                     m['permissions']['required'] + m['permissions'].get('optional', [])]
            require(main.get('browser') and not main.get('node') and not m.get('companionExecutables')
                    and not set(perms).intersection({'runtime.advanced','companion.execute','terminal.intercept.input','terminal.intercept.output'})
                    and not any(p['kind'] in ('terminal.interceptor.input','terminal.interceptor.output')
                                for p in m.get('contributes', {}).get('providers', [])), 'Browser-only admission required')
            if record['distribution'] == 'source-only':
                require('artifact' not in e and 'tag' not in record, 'Source-only cannot advertise a package/tag')
            else:
                require('artifact' in e and 'tag' in record, 'Release requires artifact and tag')
                tag, artifact = record['tag'], e['artifact']
                url_allowed(artifact['url'])
                prefix = f"https://github.com/{e['repository']}/releases/download/{tag}/"
                require(artifact['url'].startswith(prefix) and re.fullmatch(r'[A-Za-z0-9._-]+\.ncpkg', artifact['url'][len(prefix):]), 'Expected versioned GitHub ncpkg release asset')
                require(tag not in tags and artifact['url'] not in urls and artifact['sha256'] not in hashes, 'Each version needs a new tag and asset')
                tags.add(tag); urls.add(artifact['url']); hashes.add(artifact['sha256'])
            if v == plugin['current']:
                require(record['withdrawal'] is None, 'Withdrawn version cannot be current')
                catalog.append(copy.deepcopy(e))
        require(plugin['current'] is None or plugin['current'] in versions, 'Missing current version')
    if baseline is not None:
        after = {(p['id'], r['entry']['version']): r for p in data['plugins'] for r in p['versions']}
        for p in baseline['plugins']:
            for old in p['versions']:
                key = (p['id'], old['entry']['version'])
                require(key in after, 'Version history cannot be removed')
                new = after[key]
                require(json_equal({k:v for k,v in new.items() if k != 'withdrawal'},
                                   {k:v for k,v in old.items() if k != 'withdrawal'}), 'Published version metadata is immutable; publish a new version')
                if old['withdrawal'] is not None:
                    require(json_equal(new['withdrawal'], old['withdrawal']), 'Withdrawal cannot be undone or rewritten')
    return catalog

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def download(url, limit=None):
    limit = LIMIT if limit is None else limit
    require(type(limit) is int and 0 < limit <= LIMIT, 'Invalid download byte limit')
    opener = urllib.request.build_opener(NoRedirect)
    for _ in range(5):
        url_allowed(url)
        try:
            with opener.open(urllib.request.Request(url, headers={'User-Agent':'netcatty-index-validator'}), timeout=30) as response:
                content = response.read(limit + 1)
                require(len(content) <= limit, 'Package exceeds download byte limit')
                return content
        except urllib.error.HTTPError as error:
            if error.code not in (301,302,303,307,308):
                raise
            url = urllib.parse.urljoin(url, error.headers['Location'])
            error.close()
    raise ValueError('Too many redirects')

def read_manifest_bytes(content, info, central_directory_offset):
    """Bound actual DEFLATE output, independently of attacker-provided file_size.

    ZipExtFile truncates output at the central directory's declared size. Reading
    it with a bound cannot detect hidden trailing decompressed data, so inspect
    the raw member and require the complete compressed stream to match its size
    and CRC. Only stored/DEFLATE ZIP members are admitted for the manifest.
    """
    require(info.file_size <= MANIFEST_LIMIT, 'Manifest declared size exceeds limit')
    offset = info.header_offset
    require(0 <= offset and offset + 30 <= central_directory_offset, 'Truncated local ZIP header')
    fields = struct.unpack_from('<4s5H3I2H', content, offset)
    signature, _, flags, method, _, _, crc, compressed_size, size, name_size, extra_size = fields
    require(signature == b'PK\x03\x04', 'Invalid local ZIP header')
    require(flags == info.flag_bits and method == info.compress_type, 'Local/central ZIP metadata mismatch')
    require(not flags & (1 | 0x40 | 0x2000), 'Encrypted or masked ZIP member')
    require(size != 0xffffffff and compressed_size != 0xffffffff,
            'ZIP64 local manifest sizes are unsupported; repack with netcatty-plugin pack')
    # Data-descriptor archives may have zero local sizes; the central declaration
    # is still checked against actual decoded bytes below.
    if not flags & 8:
        require((crc, compressed_size, size) == (info.CRC, info.compress_size, info.file_size), 'Local/central ZIP sizes or CRC mismatch')
    start = offset + 30 + name_size + extra_size
    end = start + info.compress_size
    require(offset + 30 <= start <= end <= central_directory_offset, 'ZIP member overlaps central directory')
    name = content[offset + 30:offset + 30 + name_size]
    require(name == b'netcatty.plugin.json', 'Local manifest name mismatch')
    compressed = content[start:end]
    if method == zipfile.ZIP_STORED:
        require(len(compressed) <= MANIFEST_LIMIT, 'Manifest actual size exceeds limit')
        decoded = compressed
    elif method == zipfile.ZIP_DEFLATED:
        decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        decoded = decoder.decompress(compressed, MANIFEST_LIMIT + 1)
        require(len(decoded) <= MANIFEST_LIMIT, 'Manifest actual size exceeds limit')
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail, 'Incomplete or trailing manifest compression data')
    else:
        raise ValueError('Manifest requires stored or DEFLATE compression')
    require(len(decoded) == info.file_size, 'Manifest actual/declared size mismatch')
    require(zlib.crc32(decoded) == info.CRC, 'Manifest CRC mismatch')
    return decoded

def inspect_package(content, entry):
    require(len(content) <= LIMIT, 'Package exceeds 32 MiB')
    require(hashlib.sha256(content).hexdigest() == entry['artifact']['sha256'], 'Package SHA-256 mismatch')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        infos = archive.infolist()
        require(len(infos) <= 4096, 'Too many archive entries')
        names, size = set(), 0
        for item in infos:
            name = item.filename
            require(name not in names, 'Duplicate archive path'); names.add(name)
            require(not re.search(r'[\\:\x00]', name) and all(p not in ('', '.', '..') for p in name.rstrip('/').split('/')), 'Unsafe archive path')
            mode = item.external_attr >> 16
            require(mode & 0o170000 not in (0o120000, 0o020000, 0o060000, 0o010000), 'Nonregular archive entry')
            require(not item.flag_bits & 1, 'Encrypted archive entry')
            size += item.file_size
        require(size <= 128 * 1024 * 1024, 'Expanded package exceeds limit')
        info = archive.getinfo('netcatty.plugin.json')
        manifest_bytes = read_manifest_bytes(content, info, archive.start_dir)
        manifest = load_json(manifest_bytes)
        require(json_equal(manifest, entry['manifest']), 'Package manifest differs from index')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=pathlib.Path, default=ROOT)
    parser.add_argument('--baseline', type=pathlib.Path)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    data = read(args.root / 'index.json')
    expected = validate(data, read(args.baseline) if args.baseline else None)
    if args.write:
        (args.root / 'catalog.json').write_text(json.dumps(expected, indent=2, ensure_ascii=False)+'\n')
    require(json_equal(read(args.root / 'catalog.json'), expected), 'catalog.json must exactly match active versions; run --write')
    if args.download:
        for p in data['plugins']:
            for r in p['versions']:
                if r['distribution'] == 'release' and r['withdrawal'] is None:
                    inspect_package(download(r['entry']['artifact']['url']), r['entry'])
    print(f"Validated {len(data['plugins'])} plugins; {len(expected)} current entries")

if __name__ == '__main__':
    main()
