"""Normal static publication configuration checks. No cloud commands are run."""
import hashlib
import json
import pathlib
import re
import sys
import tempfile
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import verify_snapshot
import read_uploaded_version

ROOT = pathlib.Path(__file__).resolve().parents[1]


class PublicationWorkflowTests(unittest.TestCase):
    def test_verify_existing_complete_snapshot(self):
        root = ROOT / 'distribution/bootstrap'
        checksum = hashlib.sha256((root / 'SHA256SUMS').read_bytes()).hexdigest()
        verify_snapshot.verify(root, checksum, '32578ae27ff86f0151511478d698a1cdc12fb2e0')

    def test_pinned_structured_upload_record(self):
        # A normal static record; this does not upload or activate a Worker.
        version = '12345678-1234-1234-1234-123456789abc'
        record = {'type':'version-upload','version':1,'worker_name':'netcatty-plugins','version_id':version}
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'upload.jsonl'
            path.write_text(json.dumps(record)+'\n')
            self.assertEqual(read_uploaded_version.read_version(path), version)

    def test_workflow_trust_and_publish_scope(self):
        workflow = (ROOT / '.github/workflows/static-snapshot.yml').read_text()
        build, publish = workflow.split('\n  publish:', 1)
        self.assertNotIn('secrets.', build)
        self.assertNotIn('pull_request', workflow)
        self.assertIn('environment: cloudflare-production', publish)
        self.assertIn('needs: snapshot', publish)
        self.assertIn("github.ref == 'refs/heads/main'", publish)
        self.assertIn('artifact-ids: ${{ needs.snapshot.outputs.artifact-id }}', publish)
        self.assertIn('group: registry-static-snapshot-main', workflow)
        self.assertIn('cancel-in-progress: false', workflow)
        self.assertEqual(publish.count('CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}'), 2)
        self.assertIn('versions upload --name netcatty-plugins', publish)
        self.assertIn('versions deploy "$VERSION_ID@100" --name netcatty-plugins', publish)
        for forbidden in ('triggers deploy', '--domain', '--route', 'wrangler login', 'secret put', 'run_worker_first'):
            self.assertNotIn(forbidden, publish)
        for action in re.findall(r'uses: (\S+)', workflow):
            self.assertRegex(action, r'@[a-f0-9]{40}$')
        config = json.loads((ROOT/'wrangler.jsonc').read_text())
        self.assertEqual(config['name'], 'netcatty-plugins')
        self.assertEqual(set(config['assets']), {'directory','html_handling','not_found_handling'})
        self.assertFalse({'main','routes','route','r2_buckets','account_id'} & set(config))

    def test_locked_wrangler_version_and_integrity(self):
        package = json.loads((ROOT/'tooling/cloudflare/package.json').read_text())
        lock = json.loads((ROOT/'tooling/cloudflare/package-lock.json').read_text())
        self.assertEqual(package['devDependencies']['wrangler'], '4.152.0')
        wrangler = lock['packages']['node_modules/wrangler']
        self.assertEqual(wrangler['version'], '4.152.0')
        self.assertEqual(wrangler['integrity'], 'sha512-lmXTF1sCDEqBaEMpreGczvg/x3AIh1d/qxc4BN7utQ4jEDwdA4YG0L6kr3ev0TtVLHRb6QLySNAOAunwn+dHeA==')
        for path, metadata in lock['packages'].items():
            if path:
                self.assertIn('integrity', metadata)
                self.assertTrue(metadata['resolved'].startswith('https://registry.npmjs.org/'))


if __name__ == '__main__':
    unittest.main()
