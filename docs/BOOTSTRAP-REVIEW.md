# Bootstrap audit and pending publication

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
- typing_extensions 4.16.0 (transitive dependency; pinned on review branch)
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

## Publication and subsequent change procedure

1. User creates exactly binaricat/netcatty-plugins as a public EMPTY repository,
   without generated README, license or .gitignore. Do not change credentials or
   account security. Stop if existing content is present; preserve it and prepare
   a normal PR against that repository instead.
2. In an authorized execution environment, materialize the saved Library bundle,
   verify its supplied SHA-256, run `git bundle verify`, and clone it locally.
   Review initial main commit and review/static-download-audit separately.
3. Read the target repository metadata and refs using already authorized access.
   Confirm owner, public visibility and absence of refs immediately before push.
4. Push only `main:main` with ordinary non-force push. If another actor initialized
   main meanwhile, let the non-fast-forward rejection stop publication. Do not use
   force, delete refs, or rewrite existing remote history. If a different branch
   appears meanwhile, stop and reconcile by PR before proceeding further.
5. Push the review branch and open a PR for its audit/tests; do not auto-merge it.
   Subsequent changes always use reviewable PRs.
6. Inspect the actual main Actions run and canonical raw catalog URL. Configure
   branch/Actions review rules only through the separately authorized maintainer
   workflow. Report exact commit, run URL and checks; do not claim remote success
   from the local test results alone.

The user created the repository; account-level repository creation is not retried.
No plugin release or Netcatty app PR merge is part of publication.
