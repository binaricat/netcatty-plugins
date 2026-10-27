"""Build a deterministic, all-or-nothing static snapshot. Never execute plugin code."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.request
from jsonschema import Draft202012Validator
import validate

ROOT = pathlib.Path(__file__).resolve().parents[1]
MAX_RESOURCE = 256 * 1024
MAX_TOTAL = 16 * 1024 * 1024
HEADERS = """/*
  Access-Control-Allow-Origin: *
  X-Content-Type-Options: nosniff
  Referrer-Policy: no-referrer
  Content-Security-Policy: default-src 'none'; frame-ancestors 'none'
/v1/snapshot.json
  Cache-Control: public, max-age=60, must-revalidate
/catalog.json
  Cache-Control: public, max-age=60, must-revalidate
/index.json
  Cache-Control: public, max-age=60, must-revalidate
/delivery.json
  Cache-Control: public, max-age=60, must-revalidate
/assets/*
  Cache-Control: public, max-age=31536000, immutable
/snapshots/*
  Cache-Control: public, max-age=31536000, immutable
"""


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reject_constant(value):
    raise ValueError('Nonstandard JSON constant: ' + value)


def parse(data):
    return json.loads(data, object_pairs_hook=validate.pairs, parse_constant=reject_constant)


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode()


def git_file(ref, path):
    require(bool(re.fullmatch('[a-f0-9]{40}', ref)), 'Registry ref must be a full commit SHA')
    return subprocess.check_output(['git', 'show', f'{ref}:{path}'], cwd=ROOT)


def fetch_source(repository, commit, source_path):
    # Fixed raw origin, full source commit, no credentials or redirects.
    require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository)), 'Invalid repository')
    require(bool(re.fullmatch('[a-f0-9]{40}', commit)), 'Unpinned source commit')
    require(bool(re.fullmatch(r'[A-Za-z0-9_./-]+', source_path)) and
            all(p not in ('', '.', '..') for p in source_path.split('/')), 'Unsafe source path')
    url = f'https://raw.githubusercontent.com/{repository}/{commit}/{source_path}'
    opener = urllib.request.build_opener(validate.NoRedirect)
    with opener.open(urllib.request.Request(url, headers={'User-Agent':'netcatty-static-snapshot'}), timeout=20) as response:
        content = response.read(MAX_RESOURCE + 1)
    require(len(content) <= MAX_RESOURCE, 'Source resource exceeds 256 KiB')
    return content


def build(registry_ref, output, fetcher=fetch_source):
    output = pathlib.Path(output)
    require(not output.exists(), 'Output already exists; use a new destination')
    index_bytes = git_file(registry_ref, 'index.json')
    catalog_bytes = git_file(registry_ref, 'catalog.json')
    ledger, catalog = parse(index_bytes), parse(catalog_bytes)
    projected = validate.validate(ledger)
    require(canonical(catalog) == canonical(projected), 'Catalog differs from active ledger projection')
    # PR #2 remains unmerged. Do not introduce release-package processing through
    # the known-unhardened main validator. Enable mirroring in a later reviewed PR.
    require(all('artifact' not in e for e in catalog), 'Package mirroring is gated pending hardened validator review')
    pins_bytes = (ROOT / 'distribution/sources.json').read_bytes()
    pins = parse(pins_bytes)
    Draft202012Validator(parse((ROOT / 'schema/distribution-sources.schema.json').read_bytes())).validate(pins)
    keys = [(p['id'], p['version'], p['repository'], p['commit']) for p in pins['plugins']]
    require(len(keys) == len(set(keys)), 'Duplicate source-resource pin')
    pin_map = dict(zip(keys, pins['plugins']))
    selected = {(e['id'], e['version'], e['repository'], e['commit']) for e in catalog}
    require(set(pin_map) == selected, 'Resource pins must exactly cover current catalog')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = pathlib.Path(tempfile.mkdtemp(prefix='.snapshot-', dir=output.parent))
    total = 0
    try:
        delivery = {'schemaVersion':1, 'registryCommit':registry_ref, 'catalogSha256':sha(catalog_bytes),
                    'indexSha256':sha(index_bytes), 'sourceLockSha256':sha(pins_bytes),
                    'builderSha256':sha(pathlib.Path(__file__).read_bytes()), 'plugins':[]}
        for e in catalog:
            key = (e['id'], e['version'], e['repository'], e['commit'])
            resources = pin_map[key]['resources']
            require(resources['readme']['sourcePath'] == e['readme'], 'README pin mismatch')
            declared_icon = e['manifest'].get('icon', {})
            for theme, kind in [('light','iconLight'), ('dark','iconDark')]:
                if kind in resources:
                    require(declared_icon.get('kind') == 'package' and
                            resources[kind]['sourcePath'].endswith('/'+declared_icon.get(theme, '\0')),
                            'Icon pin must match declared package icon')
            item = {k:e[k] for k in ('id','version','repository','commit')}
            item.update({'readme':None,'iconLight':None,'iconDark':None,'avatar':None,'artifact':None})
            for kind, pin in resources.items():
                body = fetcher(e['repository'], e['commit'], pin['sourcePath'])
                require(len(body) <= MAX_RESOURCE and sha(body) == pin['sha256'], 'Resource size/hash mismatch')
                total += len(body)
                require(total <= MAX_TOTAL, 'Snapshot source resources exceed 16 MiB')
                suffix = pathlib.PurePosixPath(pin['sourcePath']).suffix
                require(suffix == '.md' if kind == 'readme' else suffix in ('.png','.webp'), 'Unsupported resource type')
                if kind == 'readme':
                    body.decode('utf-8')
                asset = f'/assets/{sha(body)}{suffix}'
                target = stage / asset.lstrip('/')
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(body)
                item[kind] = {'path':asset,'sha256':sha(body),'size':len(body)}
            delivery['plugins'].append(item)
        Draft202012Validator(parse((ROOT / 'schema/delivery.schema.json').read_bytes())).validate(delivery)
        delivery_bytes = canonical(delivery)
        snapshot_id = sha(delivery_bytes)
        snapshot_dir = stage / 'snapshots' / snapshot_id
        snapshot_dir.mkdir(parents=True)
        pointer = {'schemaVersion':1,'registryCommit':registry_ref,'snapshotId':snapshot_id}
        for name, body in [('catalog',catalog_bytes),('index',index_bytes),('delivery',delivery_bytes)]:
            filename = name + '.json'
            (snapshot_dir / filename).write_bytes(body)
            (stage / filename).write_bytes(body)
            pointer[name] = {'path':f'/snapshots/{snapshot_id}/{filename}','sha256':sha(body),'size':len(body)}
        (stage/'v1').mkdir()
        (stage/'v1/snapshot.json').write_bytes(canonical(pointer))
        (stage/'_headers').write_text(HEADERS)
        files = sorted(p for p in stage.rglob('*') if p.is_file())
        checksum = ''.join(f'{sha(p.read_bytes())}  {p.relative_to(stage).as_posix()}\n' for p in files)
        (stage/'SHA256SUMS').write_text(checksum)
        # The destination appears only after every resource and document validates.
        stage.rename(output)
        return pointer
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registry-ref', required=True)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()
    pointer = build(args.registry_ref, args.out)
    print(json.dumps(pointer, indent=2))


if __name__ == '__main__':
    main()
