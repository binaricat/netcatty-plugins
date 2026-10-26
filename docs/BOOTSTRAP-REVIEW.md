# Bootstrap audit and maintenance

Initial local bootstrap: 78606dd13261553fe8da3bdc06890ecc959223e2.
Local audit follow-up: c88d2b3d11d3f35c9e0ffb8f760ba7ad07c573ac.
The repository owner created the public empty repository and granted the existing
GitHub integration access. Initialization is performed through that integration;
no new CLI credentials were created. The initial publication includes the audit
tests and dependency pin. Hosted branch protection remains a maintainer setup step.

## Exact dependencies

- attrs 25.4.0
- jsonschema 4.26.0
- jsonschema-specifications 2025.9.1
- referencing 0.37.0
- rpds-py 0.30.0
- typing_extensions 4.16.0 (transitive dependency)
- actions/checkout 11bd71901bbe5b1630ceea73d27597364c9af683 (v4.2.2)

Python comes from ubuntu-latest on hosted CI, so interpreter/OS images are not
immutable. PyPI versions are pinned but distribution hashes are not locked;
this reduces version drift, not all dependency supply-chain risk. Local validation
used Python 3.12.14 in a fresh virtual environment. No plugin npm/pip/install/build scripts run.

## CI trust and TOCTOU boundaries

Triggers: pull_request, push to main, workflow_dispatch. Token: contents:read only;
other permissions are implicitly none. Both checkouts disable persisted credentials.
No secrets, pull_request_target, self-hosted runner, plugin code execution or upload
step is present. Job timeout is 10 minutes.

On PRs, trusted code/schema/dependencies/tests come from pull_request.base.sha.
Candidate index/catalog data come from pull_request.head.sha, never a mutable branch
name. History is compared to the exact checked-out base ledger. A moved base needs
new validation: require up-to-date branches/merge-queue validation as appropriate
before merging. The scaffold does not configure that hosted rule. PR workflow edits
can change workflow behavior; owners must inspect them and enforce platform approval.

Download redirects are checked before each request, limited to five requests. Each
request has a 30-second timeout; job timeout bounds slow multi-request cases. The
returned package is held in one bytes object: SHA-256 and ZIP/manifest inspection
use those same bytes, with no reopen/refetch between hash and inspection. No files
are extracted. Static JSON input symlinks are rejected; inputs come from immutable
Git revisions and no candidate code runs alongside the validator.

CI only checks the bytes it sees. A release asset may change or disappear later;
the app must fetch again and verify the recorded hash at installation. CI cannot
prove a source tag maps to a commit or a package was built from that commit; these
remain explicit maintainer provenance checks. Package ZIP checks are not the full
Netcatty package validator. Old catalog caches do not enforce new withdrawals;
consumers must refresh and consult the ledger before install.

## Withdrawal constraints

Version identity, manifest, compatibility, permissions, license, source commit, tag,
asset URL and digest are immutable. History deletion is rejected. Withdrawal is a
one-way null-to-record transition: timestamp/reason/advisory then cannot be rewritten
or cleared. A withdrawn version cannot be current. Set current to another reviewed
version or null and regenerate catalog.json. Listing acceptance cannot forcibly
remove an already-installed plugin. No automatic rollback/activation is performed.

## Publication evidence and ongoing changes

The public repository is initialized at
[32578ae27ff86f0151511478d698a1cdc12fb2e0](https://github.com/binaricat/netcatty-plugins/commit/32578ae27ff86f0151511478d698a1cdc12fb2e0).
The initial [GitHub Actions run](https://github.com/binaricat/netcatty-plugins/actions/runs/40278609561)
passed the static-index job, including all 28 unit tests and catalog validation.
The canonical [catalog](https://raw.githubusercontent.com/binaricat/netcatty-plugins/main/catalog.json)
was fetched without authentication and compared byte-for-byte with the published
checkout. Both initial listings remain source-only; no live release download was
available to exercise. Download policy and package inspection use synthetic tests.

For ongoing updates:

1. Branch from current main, preserve existing records and edit index.json.
2. Run tests, regenerate catalog.json, and validate against main's ledger as in README.
3. Open a reviewable PR. Require owner review and static-index success against the
   latest base. A moved base needs fresh validation before merge.
4. Review workflow, dependency, schema and validator changes separately. PR CI runs
   trusted base tooling, so proposed tooling changes also need explicit local tests.
5. After merge, inspect the actual main Actions run and canonical catalog response.
   Do not infer published success from local tests or a PR result alone.

No branch-protection/Actions approval settings were changed during bootstrap.
Configure the rules listed in MAINTAINERS.md before relying on enforced review.
This index does not publish plugin packages or merge/release Netcatty application PRs.
