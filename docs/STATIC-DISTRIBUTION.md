# Static distribution at plugins.netcatty.app

This is a separate, assets-only Cloudflare Worker. It does not change the main
website, create R2 storage, enable a paid service, or execute plugin code. The
repository PR prepares files and CI artifacts; cloud resource creation, upload,
domain binding and credentials are separate actions owned by the deployment task.
No Cloudflare token is created or configured here.

## Initial source and scope

`distribution/bootstrap/` is the complete initial upload directory. It is built
from actual registry main `32578ae27ff86f0151511478d698a1cdc12fb2e0`, not a proposed
plugin release. Its `SHA256SUMS` covers every served file and `_headers` except
itself. Check the externally supplied SHA-256 of SHA256SUMS first, then verify all
entries. Use the exact PR commit when downloading; never consume a moving branch.

The two examples remain source-only. This snapshot includes both pinned README
files and Starter's pinned light/dark brand PNGs. It contains no `.ncpkg`, no plugin
implementation code and no author avatar. Avatar is explicitly null: clients use a
bundled placeholder and never derive an avatars.githubusercontent.com URL.

PR #2's hardening remains unmerged. This first snapshot builder therefore refuses
any catalog containing an artifact. A later reviewed change, after the hardened
validator lands, can enable bounded package mirroring and extend delivery schema.
Do not make source-only examples installable or bypass that gate to deploy a package.
No blocked independent adversarial verification was repeated for this work.

## Versioned client contract

Start at `https://plugins.netcatty.app/v1/snapshot.json` (schemaVersion 1):

```text
{schemaVersion, registryCommit, snapshotId,
 catalog: {path, sha256, size}, index: {path, sha256, size},
 delivery: {path, sha256, size}}
```

Fetch only same-origin relative paths from that pointer. Verify bounds, byte counts,
hashes, schema and matching registryCommit before replacing the client's cached
snapshot. Each path is `/snapshots/<snapshotId>/<name>.json`; snapshotId equals the
SHA-256 of delivery.json. catalog.json and index.json retain their existing schemas
and bytes. The new delivery contract is in `schema/delivery.schema.json`:

```text
{schemaVersion: 1, registryCommit, catalogSha256, indexSha256,
 sourceLockSha256, builderSha256,
 plugins: [{id, version, repository, commit,
   readme: {path, sha256, size},
   iconLight: {path, sha256, size} | null,
   iconDark: {path, sha256, size} | null,
   avatar: null, artifact: null}]}
```

Bind each delivery item to the exact catalog id/version/repository/commit. Resource
paths are `/assets/<sha256>.md|png|webp`; clients must reject arbitrary URL origins,
redirects and mismatched resource hashes. README is untrusted Markdown data. Render
with HTML disabled and remote images/embedded resources blocked; never automatically
fetch a Markdown URL, GitHub API/raw URL or avatar URL. Explicit user navigation to
an upstream project link is distinct from background feature requests. No silent
GitHub fallback on errors: show unavailable/cached state and retry this origin.

The root `/catalog.json`, `/index.json`, `/delivery.json` are compatibility aliases;
new clients use the single pointer for a consistent set. Root index.json is the
fresh withdrawal ledger. Before any future install, refresh the pointer/ledger and
fail closed on withdrawal/unknown state. A stale historical snapshot cannot establish
that a version is still available. Never silently roll back or activate a plugin.

## Caching and atomicity

`_headers` sets pointer/root JSON to 60 seconds + must-revalidate; hash-addressed
assets and snapshot documents are immutable for one year. Hash addresses are never
reused with different bytes. Responses include nosniff, no-referrer and CORS for
read-only public assets. A content-security policy blocks active document content.
No Worker script, SPA fallback, redirect-to-GitHub or proxy code is included.

The builder stages every file privately, checks every source hash, and renames the
complete output directory only after validation. A failed fetch leaves no partial
output. Deploy the entire directory as ONE Workers Static Assets version and switch
to that version once. Never upload/activate individual catalog files separately.
Clients reject cross-version mixtures via pointer hashes and retry the pointer if a
previous immutable URL becomes unavailable. Prior snapshot availability is not a
permanent retention guarantee; do not assume stale assets are always retained.

## Build and trusted CI

```sh
python -m pip install -r requirements.txt
python scripts/validate.py
python -m unittest discover -s tests -p test_snapshot.py -v
python scripts/build_snapshot.py --registry-ref FULL_MAIN_COMMIT --out dist
(cd dist && sha256sum -c SHA256SUMS)
```

The output destination must not exist. `distribution/sources.json` pins every current
README/icon to a full upstream commit + hash. Resource updates are reviewed with the
catalog; no automatic tracking of upstream branches/tags. Fetches use a fixed HTTPS
raw.githubusercontent.com origin without credentials or redirects, 20-second request
timeouts, 256 KiB per resource and 16 MiB total. The CI job has a 10-minute timeout.
The schema/validator and source pins are from the checked-out, reviewed main commit.

`Build static snapshot` runs only on main push or main manual dispatch, uses a pinned
checkout/upload action, read-only token permissions, and no deployment credentials.
It verifies that the exact main commit corresponds to a merged PR, rejecting direct
pushes, then rechecks current main before exposing the complete artifact. There is
no pull_request/pull_request_target trigger for snapshot generation. The existing
untrusted PR validation workflow remains unchanged. Per-repo concurrency serializes
snapshot generation; no cancellation of an in-progress build is requested.

The automatic workflow starts only after this PR is reviewed and merged. The initial
bootstrap directory is a separately reviewable handoff based on the existing main
snapshot; it is not evidence of an already deployed domain or future auto-deployment.

## Separate deployment approval

A publisher must recheck current main immediately before deployment, verify artifact
provenance and SHA256SUMS, serialize deployments in the same publication order, and
activate one complete static version. Do not deploy a superseded queued snapshot.
Future credentialed publication must stay in the trusted-main workflow/concurrency
group with a protected environment; never attach credentials to PRs. The exact token
scope and storage require separate user approval. No DNS/domain permission belongs
in the routine publication credential once the domain is configured.

`wrangler.jsonc` only names the isolated Worker and assets directory; it does not
bind the hostname or supply account/token settings. Parent deployment owns that step,
after serving/header/hash checks pass. The existing Cloudflare connector cannot
supply the asset-upload session JWT override, so automated cloud upload is pending
an approved capability/credential route, not silently simulated.

Cloudflare references: [static assets configuration](https://developers.cloudflare.com/workers/static-assets/binding/),
[headers](https://developers.cloudflare.com/workers/static-assets/headers/).
