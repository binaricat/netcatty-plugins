# Version withdrawals

Keep every version record forever. To withdraw a version, replace its null
`withdrawal` with:

```json
{
  "at": "2026-10-26T06:00:00Z",
  "reason": "Concise factual explanation",
  "advisory": "https://github.com/OWNER/REPO/issues/NUMBER"
}
```

This is a structural example, not an actual advisory. Use a real public advisory or
issue. Never put undisclosed exploit details, credentials or private reports in the
public ledger. A withdrawal is permanent; corrections are discussed in the linked
advisory, while the original record is preserved. Recovery uses a new version.

If the withdrawn version is current, select a reviewed non-withdrawn version or set
`current` to null. Regenerate `catalog.json`; a null selection removes the entire
plugin from the current catalog, but keeps its ledger history. Historical pinned
commits, tags, hashes and manifests remain unchanged. Do not delete the version.

The current catalog alone cannot notify already-installed users of historical
withdrawals. Applications that implement withdrawal notifications must additionally
fetch `index.json` and inspect `plugins[].versions[].withdrawal` against installed
ID/version pairs. They must not silently reinstall, execute or remove local files.
Previously cached catalogs may still contain a withdrawn version; consumers should
refresh and check the ledger before installation. Offline/stale behavior must be an
explicit product decision in the app integration, not inferred from this repository.
