"""Read-only main/merged-PR gate using the workflow's scoped ephemeral token."""
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

REPOSITORY = 'binaricat/netcatty-plugins'


def check(commit):
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Expected exact commit SHA')
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise ValueError('Publication gate requires the workflow GitHub token')
    result = subprocess.check_output(['git', 'ls-remote', f'https://github.com/{REPOSITORY}.git',
                                      'refs/heads/main'], text=True, timeout=30,
                                     env={k:v for k,v in os.environ.items() if k != 'GITHUB_TOKEN'})
    if result.split()[0] != commit:
        raise ValueError('Superseded main snapshot; refuse publication')
    request = urllib.request.Request(f'https://api.github.com/repos/{REPOSITORY}/commits/{commit}/pulls',
                                     headers={'Accept':'application/vnd.github+json','User-Agent':'netcatty-snapshot',
                                              'Authorization':'Bearer ' + token})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            data = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        # Never log response bodies, arbitrary headers or the request token.
        details = []
        if error.code in (403, 429):
            for name in ('Retry-After', 'X-RateLimit-Remaining', 'X-RateLimit-Reset'):
                value = error.headers.get(name, '') if error.headers else ''
                if re.fullmatch(r'[0-9]{1,20}', value):
                    details.append(f'{name}={value}')
        error.close()
        raise ValueError(f'GitHub publication gate HTTP {error.code}; ' +
                         '; '.join(details) + '; no automatic retry') from None
    if len(data) > 1024 * 1024:
        raise ValueError('PR metadata exceeds limit')
    prs = json.loads(data)
    if not any(p.get('merged_at') and p['base']['ref'] == 'main' and
               p.get('merge_commit_sha') == commit for p in prs):
        raise ValueError('Snapshot CI requires a merged PR on main; direct pushes are not publishable')
    print('Confirmed current main and merged PR:', commit)


if __name__ == '__main__':
    check(sys.argv[1])
