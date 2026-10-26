# Netcatty plugin index

A public, reviewable directory of Netcatty plugins. This repository stores metadata,
version history and submission rules. Plugin source and `.ncpkg` packages stay in
the publisher's repository; they are not merged into Netcatty.

## Consumer contract

Canonical endpoint:

`https://raw.githubusercontent.com/binaricat/netcatty-plugins/main/catalog.json`

`catalog.json` is a JSON array, with at most one selected, non-withdrawn version per
plugin ID. It retains the shape read by Netcatty Draft #3949 at
`4445c292ea70c9aa53ce0fd5b5af681acb124bf8`:

```text
{id, version, name, description, author, repository, commit, license, readme,
 manifest, artifact?: {url, sha256}}
```

`repository` is `owner/repo`; `commit` is a full lowercase 40-character source SHA;
`readme` is a safe repository-relative Markdown path. `manifest` is the full public
Netcatty manifest, including `engines.netcatty`, `engines.api`, permissions and license.
`artifact` is omitted for source-only examples. Never treat them as installable.
The initial entries are copied verbatim from that reviewed source snapshot; no
published package is claimed. The schema is vendored from the same Netcatty commit,
under its GPL-3.0-or-later license (see LICENSE); no third-party plugin implementation
is vendored. This repository's rules and tooling use GPL-3.0-or-later as well.

`index.json` is the authoritative version ledger; `catalog.json` is its checked
projection. See [schema](schema/index.schema.json), [author workflow](CONTRIBUTING.md),
[maintenance checklist](docs/MAINTAINERS.md) and [withdrawals](docs/WITHDRAWALS.md).
The app integration is separate: the referenced Draft currently bundles its catalog.
This repository does not change that app or claim remote fetching is already shipped.
Consumers must validate fetched metadata, bound downloads, verify hashes at install,
handle unavailable/invalid responses and never auto-enable plugins.

## Local checks

Use Python 3.12 or newer in a virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/validate.py
# After editing index.json:
python scripts/validate.py --write
# Compare with an index.json saved from the PR base:
python scripts/validate.py --baseline /path/to/base-index.json --download
```

Download checks only fetch versioned GitHub release assets, follow bounded redirects
through approved HTTPS GitHub asset hosts, enforce byte limits and SHA-256, and
inspect the ZIP and manifest without extraction or execution. They do not build,
install or run plugins. No package exists for the initial entries, so the initial
`--download` check performs no network downloads. Tests use synthetic in-memory ZIPs.

Passing checks establish metadata consistency and some distribution constraints.
They are not a security certification, a provenance guarantee, or a legal opinion.
Maintainers review source provenance, licensing and behavior before accepting entries.
