# Submit or update a plugin

1. Keep your source, license, build instructions and release assets in your own
   public repository. Publish a new semantic version, a new immutable tag and a new
   `.ncpkg` asset for every release. Never retarget tags or replace released bytes.
2. Record the full source commit, exact tag, release URL and lowercase SHA-256 of
   the actual `.ncpkg`. The URL must be
   `https://github.com/OWNER/REPO/releases/download/TAG/NAME.ncpkg`.
   Provide evidence that the tag resolves to the pinned commit and describe how
   the package was built from it. CI hashes bytes; maintainers verify provenance.
3. Add a version to `index.json` and select it with `current`. Include the complete
   package manifest, app/API compatibility ranges, license and required/optional
   permissions. Explain each permission in the PR. Browser-only admission matches
   the normal Netcatty path; Node, companions and interceptors are not admitted.
4. A source-only listing has `distribution: "source-only"`, no `artifact`, no `tag`,
   and `withdrawal: null`. Do not invent a release URL or digest. Once recorded,
   even a source-only version is immutable: a later packaged publication uses a
   new version. Source-only does not mean executable or installable from the market.
5. Run the commands in README. Commit the generated `catalog.json` with the ledger.
   Open a PR using the template. Do not include binaries, implementation source,
   generated build directories, secrets, or unrelated workflow changes.
6. Await maintainer review. Future updates always use reviewable PRs. CI compares
   against the base ledger and rejects deletions, reused versions, changed hashes,
   source commits, manifests, tags and artifact URLs. Existing metadata corrections
   require a new version; withdrawal metadata is the narrowly defined exception.

Metadata is not permission approval. Netcatty still performs package validation and
asks the user to grant applicable permissions. Include accurate license information;
listing does not transfer ownership or certify that a license applies to all contents.

Infrastructure changes belong in separate PRs. Untrusted PR CI intentionally runs
base validator code and base tests, so test proposed validator/schema changes locally
and have a maintainer inspect them before merge. Do not run PR-provided build scripts.

## Supported package representation

This pre-release `.ncpkg` format supports bounded ordinary ZIP32 packages, as
produced by the current Netcatty CLI. ZIP64 is not supported in this release,
even when the actual files are small. A valid general-purpose ZIP archive is not
necessarily a supported `.ncpkg` package.

Use the existing `netcatty-plugin pack <directory> --out <package.ncpkg>` command
after preparing the plugin files; keep the output outside the source directory.
The canonical packer writes stored entries with UTF-8 names, ordinary 32-bit
sizes/offsets and matching local/central metadata, without data descriptors or
ZIP64 extras. The app also validates entrypoints, resources and other package
constraints. Registry ZIP checks are only static admission checks, not a substitute
for app/CLI validation and not a promise to accept other ZIP encoders' features.

This clarification does not enable package mirroring or make the initial
source-only entries installable.
