# Maintainer guide

## Repository setup after publication

Require PRs, owner review and the `static-index` check for main; disallow force pushes
and deletion. Require approval after new commits. Restrict Actions to reviewed actions
and read-only default token permissions; require approval of workflows from external
contributors. CODEOWNERS requests review but does not enforce it without repository
rules. These hosted settings are not configured by this local scaffold.

The workflow uses `pull_request`, never `pull_request_target`, no secrets, no write
permissions, no self-hosted runner, no plugin execution and no persisted checkout
credentials. PR validation runs code/dependencies/tests from the base SHA; candidate
checkout provides only JSON inputs. No candidate dependency install or shell script
runs. Downloads are public and unauthenticated. The runner's job timeout bounds
slow transfers. Every redirect must remain on the allowlist.

GitHub reads workflow definitions from PRs: workflow edits themselves require careful
review and the platform approval policy. Do not approve an untrusted workflow change
merely because the default workflow is safe. Review infrastructure separately and
never pass a write token or secret into contributor-controlled code.

## Review every listing/update

- [ ] Confirm repository owner/publisher authorization and the upstream license.
- [ ] Read the source at the pinned commit; check the tag resolves to that commit,
      build instructions/provenance and release asset ownership. Compare the upstream
      manifest against the ledger. Do not execute third-party build/install scripts.
- [ ] Check app/API compatibility, permissions and their justification; examine data
      access, network destinations, filesystem/terminal effects, dependencies and
      unexpected binaries. Browser-only does not imply harmless behavior.
- [ ] Check the actual artifact SHA-256 and package manifest. Run bounded download
      validation. Inspect declared asset sizes/types and package content statically;
      the index ZIP checks are deliberately not the full Netcatty package validator.
- [ ] Confirm each version has a unique immutable tag/asset and no old metadata changed.
- [ ] Verify current selection, generated catalog and withdrawal state. Confirm no
      source-only listing implies an available package.
- [ ] Review workflow/schema/tooling changes separately. Test code changes locally;
      PR CI only executes trusted base tooling. Audit pinned dependency/action updates.
- [ ] Approve/merge only after review. Acceptance does not certify security or legality.

## Maintenance

Use PRs for all changes after initial bootstrap. Keep the public contract schema pinned
and document its Netcatty source commit when upgrading. Run tests and compare projected
catalogs against the application consumer. Never weaken historical immutability to
repair a package: withdraw it and publish a new version. Periodically recheck active
release assets for disappearance or changed bytes; index CI runs on PR/push/manual
triggers, not a continuous availability monitor. Investigate hash mismatches instead
of replacing the recorded digest. Do not publish releases from this index repository.
