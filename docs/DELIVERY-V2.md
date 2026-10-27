# Reviewed marketplace delivery v2

The committed `distribution/sources.json` keeps `deliveryVersion: 1`. This
continues source-only publication with null avatar/artifact fields, even though
the reviewed project-avatar pin is prepared. Do not change it to 2 until the
application accepts v2 avatars/packages and end-to-end acceptance is complete.
This change publishes no package, tag, release or non-null avatar.

## Data and trust

The pointer remains `/v1/snapshot.json`. A v2 delivery uses the existing fields:
`avatar: null | {path, sha256, size}` and
`artifact: null | {path, sha256, size}`. Avatar paths are
`/assets/<sha256>.png|webp` (1–262144 bytes); package paths are
`/assets/<sha256>.ncpkg`. The snapshot ID hashes delivery bytes; document hashes,
source-lock hash, builder hash and the full checksum manifest bind the output.
Publication verifies all referenced resource bytes, sizes and hashes again.

Canonical `index.json` retains immutable GitHub release URL/tag/source-commit/hash
provenance. It is validated before any download. The generated CDN index/catalog
are copies with artifact URLs deterministically rewritten to
`https://plugins.netcatty.app/assets/<sha256>.ncpkg`; other metadata is unchanged.
Historical entries keep their records, but only current non-withdrawn artifacts
are downloaded into a new snapshot. Historical URLs are not availability promises.
Clients must refresh the withdrawal/current-version view before installation and
recheck it before committing an install. Immutable cached bytes do not override
withdrawals. The app still performs its full package validation and permission flow.

The publisher fetches each current package once, enforces its remaining snapshot
byte budget, verifies its SHA-256 and statically inspects those same bytes with the
hardened validator. It neither builds, extracts nor executes plugin code. The
complete unique-resource budget stays 16 MiB, including packages, documents and
avatars, below Workers' 25 MiB individual asset limit. A failure discards the staged
snapshot. Existing trusted-main/merged-PR gates, serialized publication, short
pointer cache and immutable resource cache remain in place.

## Author and avatar pins

An optional per-plugin `authorSubject` names an explicitly reviewed entry in
`authors`. Its `displayName` must equal the catalog's author. Repository ownership
is never used to infer the author. The mapping does not claim personal identity
verification or grant an official badge.

An author's avatar is null or a reviewed `source`, SHA-256, exact byte `size` and
`format` (`png` or `webp`). Sources are either a repository/full-commit/path tuple
or a numeric GitHub user ID. The latter requires subject `github-user:<id>` and
uses only the fixed public avatars.githubusercontent.com origin, with no redirects,
credentials or GitHub API request. Account-avatar content can change: a hash/size
mismatch fails publication and requires a reviewed pin update, never a silent
replacement. CI checks bounded bytes and raster signatures; the app must still
decode through its bounded rasterizer/cache. Unmapped authors and explicit null
avatars retain the default icon. Missing or changed *pinned* images fail the build.

Prepared project identity for both current entries:

- subject: `project:netcatty`; display author: `Netcatty`
- source: `binaricat/Netcatty`, commit
  `933bc93fc3b3027209955c38f1e30a7daf2e5fc0`, `build/icons/128x128.png`
- PNG 128×128, 7843 bytes; SHA-256
  `cc680bf53f845ef999a78f26f874b984fe4f66a8a97a73d9640f57365b3af7d2`

This is the project's cat icon, not binaricat's personal avatar. Host-controlled
official badges are limited to the built-in official source plus exact pairs
`com.netcatty.starter` / `binaricat/Netcatty` and
`com.netcatty.hello` / `binaricat/Netcatty`. Author text, publisher text and ID
prefixes alone are insufficient. The registry emits no badge flag.

## Acceptance and enablement order

1. Review this implementation with the gate still at 1. Offline v2 fixtures use
   small synthetic archives, never installable/public release claims.
2. The app owner aligns the v2 avatar schema, rasterizer and same-origin download
   checks. Test install/update/refusal, offline browse-only behavior, selection
   changes, source identity and withdrawal during download. No GitHub fallback.
3. Separately approve a dedicated first-party sample release repository and exact
   source versions/tags. Do not place plugin-example releases in the desktop app's
   release feed. Build from reviewed source and lockfiles, use canonical ZIP32
   packing, record actual hashes and obtain release-publication approval.
4. Add new immutable release versions and reviewed pins, then change the delivery
   gate to 2 in a reviewed follow-up. Existing source-only versions stay unchanged.
   Coordinate this publication with application acceptance; existing preview
   clients that only accept null avatars must not receive non-null avatars early.

The historical bootstrap remains byte-for-byte unchanged. Rebuilding its frozen
inputs with new builder code necessarily changes `builderSha256` and `snapshotId`;
tests compare all other delivery fields and independently verify every output
hash/size, rather than pretending new code is the original builder.
