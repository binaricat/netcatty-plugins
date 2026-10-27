"""Read Wrangler 4.152.0's structured output, never parse human-facing log lines."""
import json
import pathlib
import re
import sys


def read_version(path):
    content = pathlib.Path(path).read_bytes()
    if len(content) > 1024 * 1024:
        raise ValueError('Wrangler output exceeds limit')
    records = [json.loads(line) for line in content.decode().splitlines() if line.strip()]
    uploads = [r for r in records if r.get('type') == 'version-upload']
    if len(uploads) != 1 or uploads[0].get('version') != 1 or uploads[0].get('worker_name') != 'netcatty-plugins':
        raise ValueError('Expected exactly one upload for the isolated registry Worker')
    version_id = uploads[0].get('version_id', '')
    if not re.fullmatch(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', version_id):
        raise ValueError('Invalid uploaded version ID')
    return version_id


if __name__ == '__main__':
    print(read_version(sys.argv[1]))
