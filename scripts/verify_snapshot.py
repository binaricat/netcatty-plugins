"""Verify the complete build artifact before granting publication credentials."""
import argparse
import hashlib
import json
import pathlib
import re


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(root, expected_manifest_sha, registry_commit):
    root = pathlib.Path(root)
    manifest = (root / 'SHA256SUMS').read_bytes()
    if digest(manifest) != expected_manifest_sha:
        raise ValueError('Snapshot manifest does not match the trusted build job output')
    listed = set()
    for line in manifest.decode().splitlines():
        checksum, path = line.split('  ', 1)
        if not re.fullmatch('[a-f0-9]{64}', checksum) or path in listed:
            raise ValueError('Invalid checksum entry')
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', path) or any(p in ('', '.', '..') for p in path.split('/')):
            raise ValueError('Invalid snapshot path')
        candidate = root / path
        if candidate.is_symlink() or not candidate.is_file() or digest(candidate.read_bytes()) != checksum:
            raise ValueError('Snapshot file does not match manifest: ' + path)
        listed.add(path)
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != listed | {'SHA256SUMS'}:
        raise ValueError('Snapshot has missing or unlisted files')
    pointer = json.loads((root / 'v1/snapshot.json').read_bytes())
    if pointer['registryCommit'] != registry_commit or pointer['snapshotId'] != digest((root/'delivery.json').read_bytes()):
        raise ValueError('Snapshot provenance mismatch')
    for name in ('catalog', 'index', 'delivery'):
        record = pointer[name]
        path = f"/snapshots/{pointer['snapshotId']}/{name}.json"
        content = (root / (name + '.json')).read_bytes()
        if record['path'] != path or path.lstrip('/') not in listed or record['sha256'] != digest(content) or record['size'] != len(content):
            raise ValueError('Snapshot pointer does not match verified files')
        if (root / path.lstrip('/')).read_bytes() != content:
            raise ValueError('Snapshot aliases disagree')
    print('Verified complete static snapshot for', registry_commit)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=pathlib.Path)
    parser.add_argument('--manifest-sha', required=True)
    parser.add_argument('--registry-ref', required=True)
    args = parser.parse_args()
    verify(args.root, args.manifest_sha, args.registry_ref)
