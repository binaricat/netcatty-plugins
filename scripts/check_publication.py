"""Read-only main/merged-PR gate. No credentials or mutable workflow input."""
import json
import re
import subprocess
import sys
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

REPOSITORY = 'binaricat/netcatty-plugins'


def check(commit):
    if not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Expected exact commit SHA')
    result = subprocess.check_output(['git', 'ls-remote', f'https://github.com/{REPOSITORY}.git',
                                      'refs/heads/main'], text=True, timeout=30)
    if result.split()[0] != commit:
        raise ValueError('Superseded main snapshot; refuse publication')
    request = urllib.request.Request(f'https://api.github.com/repos/{REPOSITORY}/commits/{commit}/pulls',
                                     headers={'Accept':'application/vnd.github+json','User-Agent':'netcatty-snapshot'})
    with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('PR metadata exceeds limit')
    prs = json.loads(data)
    if not any(p.get('merged_at') and p['base']['ref'] == 'main' and
               p.get('merge_commit_sha') == commit for p in prs):
        raise ValueError('Snapshot CI requires a merged PR on main; direct pushes are not publishable')
    print('Confirmed current main and merged PR:', commit)


if __name__ == '__main__':
    check(sys.argv[1])
