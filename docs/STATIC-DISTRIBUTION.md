# Static distribution at plugins.netcatty.app

This is a separate, assets-only Cloudflare Worker. It does not change the main
website, create R2 storage, enable a paid service, or execute plugin code. The
repository PR prepares files and a guarded publication job. Worker shell creation,
initial domain binding and credential configuration remain separate approved actions.
No Cloudflare token or GitHub environment is created or configured by this PR.

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

`Build and publish static snapshot` runs only on main push or main manual dispatch.
Its build job uses pinned actions, read-only token permissions and no Cloudflare
credentials. The publication job is isolated behind the `cloudflare-production`
GitHub environment and only runs cloud commands when its approved configuration
is present.
It verifies that the exact main commit corresponds to a merged PR, rejecting direct
pushes, then rechecks current main before exposing the complete artifact. There is
no pull_request/pull_request_target trigger for snapshot generation. The existing
untrusted PR validation workflow remains unchanged. One workflow-level concurrency group serializes the entire build/publication run;
no cancellation of an in-progress publication is requested. Pending runs may be
coalesced by GitHub; only the latest still-current main is publishable.

The automatic workflow starts only after this PR is reviewed and merged. The initial
bootstrap directory is a separately reviewable handoff based on the existing main
snapshot; it is not evidence of an already deployed domain or future auto-deployment.

## Guarded publication job (not run during PR preparation)

The `publish` job depends on the successful snapshot job and uses GitHub environment
`cloudflare-production`. It downloads the exact artifact ID from that build job,
checks SHA256SUMS against the build job's digest, verifies the complete file set and
source commit, and rechecks current main / merged-PR provenance. There is no artifact
lookup by user-supplied URL, branch, latest run, or external workflow event.

Wrangler is fixed to 4.152.0 with a committed npm lockfile including dependency
integrities. Checkout, download/upload artifact, and setup-node actions are fixed to
commit SHAs. Dependencies install with `npm ci --ignore-scripts` before any Cloudflare
token is exposed. Ordinary configuration tests do not invoke Wrangler or cloud APIs.

Publication uses `wrangler versions upload` to upload one complete assets version
without activating it. It reads the exact version ID from Wrangler's structured
version-upload record, then rechecks the complete artifact and current main immediately
before `wrangler versions deploy <exact-id>@100 --yes`. It never deploys a floating
latest version. It does not invoke `triggers deploy`, routes, custom-domain, DNS,
R2, billing, login or token commands. Failed checks stop activation; an uploaded but
inactive version may remain if main changed while uploading. No automatic retry,
rollback, credential broadening or account fallback is configured.

### User-owned configuration, separately approved

Before merging/enabling publication, the user configures the repository's GitHub
**Environment** named exactly `cloudflare-production`:

- Restrict deployment branches to `main`; configure environment review appropriate
  for the single maintainer (do not require a different reviewer who does not exist).
- Environment secret: `CLOUDFLARE_API_TOKEN`.
- Environment variable: `CLOUDFLARE_ACCOUNT_ID`.
- Token selection: the existing **netcatty-plugins** Worker only, **Editor** role.
  No account-wide Worker access, DNS/domain, R2 or billing permissions are requested.

The account ID must be the real selected Cloudflare account, not a guessed value.
Do not paste credentials into an issue, PR, chat, repository file, command argument or
workflow log. This PR does not create the environment, configure values, request a
token, or assume any already exists. With missing configuration the publication job
records **skipped, no upload/deployment attempted** and executes no cloud commands.
A green build or skipped publication is not deployment evidence.

### First activation and single publisher

1. The separately approved cloud task creates the named undeployed Worker shell so
   the user can select that Worker when granting the narrow token. Do not create it
   implicitly via a broader credential. `versions upload` requires an existing Worker.
2. Before initial publication, inspect the draft, exact registry snapshot and hashes.
   The parent owns review/merge and explicit credential-setup approval. This task
   performs neither. Do not run the draft workflow to test credentials.
3. After approval, merge the reviewed PR into main. Its successful build and the
   configured environment allow the first complete static version upload/activation.
   For manual bootstrap using the same reviewed source, populate `dist` from the
   verified `distribution/bootstrap` directory, verify its externally supplied
   SHA256SUMS digest and all files, then use the same pinned Wrangler version and
   version-upload/exact-version activation sequence. The deployment operator must
   authorize that one-off operation; no separate competing publisher should remain.
4. The cloud task verifies actual serving, hashes and headers, then binds
   `plugins.netcatty.app` separately. CI never binds or edits the domain. Keep main
   website resources untouched.
5. Ongoing publication has exactly one owner: this trusted-main workflow and its
   concurrency group. Do not enable a parallel Cloudflare automatic Git publisher.
   Environment waits are included in serialization; freshness is checked again after
   waiting and before activation. A main update can still occur immediately after a
   check; the next queued current-main run supersedes it. Cross-service transactional
   locking is not claimed.

`wrangler.jsonc` names only the isolated assets Worker and local output directory.
It has no Worker script, dynamic proxy, run_worker_first, route or domain binding.
Cloudflare deployment remains unverified until an actual authorized run succeeds.
The connector's asset-session-JWT limitation is not bypassed: the future job uses
only the separately approved, restricted token through official pinned Wrangler.

Cloudflare references: [static assets configuration](https://developers.cloudflare.com/workers/static-assets/binding/),
[headers](https://developers.cloudflare.com/workers/static-assets/headers/),
[version upload and deployment commands](https://developers.cloudflare.com/workers/wrangler/commands/workers/).
