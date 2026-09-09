"""Exercise externally signed candidate-to-canonical CLI operations end to end."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest


class AdvancedWorkflowTests(unittest.TestCase):
    def test_signed_canonical_integration_through_public_cli(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='vera-advanced-workflow-') as temporary:
            output = Path(temporary) / 'example'
            process = subprocess.run([sys.executable, str(root / 'examples/advanced-workflow.py'),
                '--output', str(output), '--cross', os.environ['VERANTYX_CROSS'],
                '--precedent', os.environ['VERANTYX_PRECEDENT']], cwd=root, text=True,
                capture_output=True, stdin=subprocess.DEVNULL, timeout=180)
            report = json.loads((output / 'report.json').read_text())
            self.assertEqual(process.returncode, 0, report)
            self.assertTrue(report['passed'])
            self.assertTrue(all(row['passed'] for row in report['checks']))
            self.assertTrue(report['integration']['signature_mode'])
            self.assertEqual(report['integration']['receipt']['outcome'], 'INTEGRATED')
            self.assertEqual(report['live_model_calls'], 0)
            self.assertEqual(report['fixture_key'], 'EPHEMERAL_SYNTHETIC_PRIVATE_KEY_NOT_SAVED')
