"""Actual CLI integration audit. All keys, projects and effects are synthetic.

The source under inspection defaults to this checkout. Set
VERANTYX_AUDIT_SOURCE to another checkout's src directory without copying this
test there. VERANTYX_AUDIT_LOG_DIR optionally retains command transcripts.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


class ProcessCLIAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="verantyx-cli-process-audit-")
        self.root = Path(self.temporary.name).resolve()
        self.source = Path(os.environ.get("VERANTYX_AUDIT_SOURCE", str(Path(__file__).resolve().parents[1] / "src"))).resolve()
        self.environment = {**os.environ, "PYTHONPATH": str(self.source), "PYTHONDONTWRITEBYTECODE": "1"}
        self.precedent = os.environ["VERANTYX_PRECEDENT"]
        self.calls = []
        self.sequence = 0
        self.base = [sys.executable, "-m", "verantyx", "--project", str(self.root)]
        self.call(["setup", "--non-interactive", "--name", "CLI process audit"])
        (self.root / "candidate.py").write_text("def answer(value):\n    return value * 2\n")
        self.target = self.root / "artifact.txt"
        self.target.write_text("before")
        first = self.call(["run", "Artificial integration audit", "--task-id", "audit", "--observe", "candidate.py",
                           "--observe", "artifact.txt", "--key", "task"])
        proposal = {"schema_version": 1, "task_id": "audit", "context_revision": first["state"]["revision"],
                    "response_locale": "ja", "summary": "Artificial proposal", "claims": [{"id": "doubling", "statement": "A finite fixture only",
                    "source_refs": [first["state"]["latest_observations"]["candidate.py"]]}], "actions": [], "unknowns": []}
        self.write("proposal.json", proposal)
        self.call(["resume", "audit", "--proposal", str(self.root / "proposal.json"), "--key", "proposal"])
        self.oracle_spec = self.root / "oracle-spec.json"
        self.write(self.oracle_spec, {"claim_id": "doubling", "target_path": "candidate.py", "function": "answer", "property": "21 maps to integer 42",
                   "cases": [{"id": "positive", "input": 21, "expected": 42}],
                   "negative_controls": [{"id": "counterexample", "case_id": "positive", "counterexample": 41}],
                   "oracle": {"description": "Artificial finite arithmetic contract", "source_refs": []},
                   "provenance": {k: "" for k in ("model", "provider", "implementation", "dependencies", "oracle", "data", "environment")},
                   "timeout": 2, "max_output": 4096})
        self.executor = self.root / "executor.py"
        self.executor.write_text("import json,sys\nfrom pathlib import Path\nvalue=json.load(sys.stdin)\nPath('artifact.txt').write_text(value['text'])\nwith Path('calls.txt').open('a') as output: output.write('called\\n')\nprint('complete')\n")
        self.command_file = self.root / "command.json"
        self.write(self.command_file, {"argv": [sys.executable, str(self.executor)], "cwd": str(self.root)})
        self.command_spec = self.root / "command-spec.json"
        self.write(self.command_spec, {"description": "Artificial local file effect", "effect_class": "REVERSIBLE_LOCAL",
                   "targets": ["artifact.txt"], "external_target": "", "input": {"text": "after"},
                   "timeout": 2, "max_output": 4096, "dependencies": [], "compensation": "Restore the fixture after review"})
        # A private key exists only in this artificial test harness, never in
        # a product command or user store. It does not represent user consent.
        self.key = Ed25519PrivateKey.generate()
        self.public = self.root / "artificial-public.pem"
        self.public.write_bytes(self.key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    def tearDown(self):
        directory = os.environ.get("VERANTYX_AUDIT_LOG_DIR")
        if directory:
            path = Path(directory)
            path.mkdir(parents=True, exist_ok=True)
            (path / (self._testMethodName + ".json")).write_text(json.dumps({"test": self.id(), "source": str(self.source),
                "fixtures_only": True, "live_model_calls": 0, "external_network_calls": 0, "calls": self.calls}, ensure_ascii=False, indent=2) + "\n")
        self.temporary.cleanup()

    def write(self, name, value):
        path = Path(name)
        if not path.is_absolute():
            path = self.root / path
        path.write_text(json.dumps(value, ensure_ascii=False))
        return path

    def call(self, args, error=None, locale="ja", text=False):
        argv = [*self.base, "--lang", locale, *([] if text else ["--json"]), *args]
        process = subprocess.run(argv, cwd=self.root, env=self.environment, capture_output=True, text=True, timeout=30)
        self.calls.append({"argv": argv, "returncode": process.returncode, "stdout": process.stdout, "stderr": process.stderr})
        self.assertNotIn("Traceback", process.stderr)
        if text:
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertTrue(process.stdout.strip())
            return process.stdout
        try:
            value = json.loads(process.stdout)
        except ValueError:
            self.fail(process.stdout + process.stderr)
        if error is not None:
            self.assertNotEqual(process.returncode, 0, value)
            self.assertEqual(value["error"]["code"], error, value)
        else:
            self.assertEqual(process.returncode, 0, value)
            self.assertTrue(value.get("ok", True), value)
        return value

    def request(self, argv):
        self.sequence += 1
        invocation = self.write("invocation-" + str(self.sequence) + ".json", {"argv": argv})
        approval = self.root / ("approval-" + str(self.sequence) + ".json")
        result = self.call(["authority-request", "--invocation", str(invocation), "--output", str(approval)])
        # Sign exactly the reviewable bytes produced by the CLI.
        signature = self.root / ("signature-" + str(self.sequence) + ".bin")
        signature.write_bytes(self.key.sign(approval.read_bytes()))
        return approval, signature, result["approval"]

    def execute_approval(self, approval, signature, error=None):
        return self.call(["authority-execute", "--approval", str(approval), "--signature", str(signature)], error=error)

    def signed(self, argv, error=None):
        approval, signature, _ = self.request(argv)
        result = self.execute_approval(approval, signature, error=error)
        return result if error else result["result"]

    def enable(self):
        self.call(["authority-enable", "--public-key", str(self.public)], error="AUTHORITY_REQUIRED")
        result = self.signed(["authority-enable", "--public-key", str(self.public)])
        self.assertTrue(result["enabled"])

    def oracle_plan_argv(self):
        return ["oracle-plan", "audit", "--spec", str(self.oracle_spec), "--precedent", self.precedent, "--key", "oracle-plan"]

    def oracle_run_argv(self, planned):
        return ["oracle-run", "audit", "--oracle", planned["oracle_id"], "--precedent", self.precedent, "--key", "oracle-run"]

    def command_plan_argv(self):
        return ["command-propose", "audit", "--spec", str(self.command_spec), "--command-file", str(self.command_file), "--key", "command-plan"]

    def command_authorize_argv(self, planned, trust=True):
        return ["command-authorize", "audit", "--effect", planned["command_effect_id"], "--plan-hash", planned["plan_hash"],
                "--command-file", str(self.command_file), "--reason", "Artificial fixture permission", "--key", "command-authorize",
                *(["--accept-unsandboxed"] if trust else [])]

    def command_execute_argv(self, planned):
        return ["command-execute", "audit", "--effect", planned["command_effect_id"], "--command-file", str(self.command_file), "--key", "command-execute"]

    def assert_once(self):
        self.assertEqual(self.target.read_text(), "after")
        self.assertEqual((self.root / "calls.txt").read_text(), "called\n")

    def test_actual_cli_legacy_workflow_and_five_language_readouts(self):
        planned = self.call(self.oracle_plan_argv())
        checked = self.call(self.oracle_run_argv(planned))
        self.assertEqual(checked["oracle"]["receipt"]["result"]["closure"], "BOUNDED")
        self.assertFalse(checked["oracle"]["receipt"]["result"]["adoption_authorized"])
        effect = self.call(self.command_plan_argv())
        self.assertEqual(self.target.read_text(), "before")
        self.call(self.command_execute_argv(effect), error="COMMAND_NOT_AUTHORIZED")
        self.call(self.command_authorize_argv(effect, trust=False), error="COMMAND_TRUST_REQUIRED")
        self.call(self.command_authorize_argv(effect))
        self.assertEqual(self.target.read_text(), "before")
        executed = self.call(self.command_execute_argv(effect))
        self.assertEqual(executed["command_effect"]["status"], "PROCESS_COMPLETED")
        self.assertEqual(executed["command_effect"]["receipt"]["process"]["effect_confirmation"], "NOT_ASSESSED")
        self.assertTrue(self.call(self.command_execute_argv(effect))["duplicate"])
        self.assert_once()
        for locale in ("en", "ja", "zh-Hans", "ko", "es"):
            for argv in (["oracles", "audit"], ["command-effects", "audit"], ["events", "audit"], ["--help"]):
                self.call(argv, locale=locale, text=True)

    def test_signed_mode_requires_each_operation_and_separate_effect_permission(self):
        self.enable()
        self.call(self.oracle_plan_argv(), error="AUTHORITY_REQUIRED")
        planned = self.signed(self.oracle_plan_argv())
        self.call(self.oracle_run_argv(planned), error="AUTHORITY_REQUIRED")
        checked = self.signed(self.oracle_run_argv(planned))
        self.assertEqual(checked["oracle"]["receipt"]["result"]["closure"], "BOUNDED")
        self.call(self.command_plan_argv(), error="AUTHORITY_REQUIRED")
        effect = self.signed(self.command_plan_argv())
        self.assertEqual(self.target.read_text(), "before")
        # An authentic operator signature to execute is still not an effect
        # authorization: the effect's own authorization event must exist first.
        self.signed(self.command_execute_argv(effect), error="COMMAND_NOT_AUTHORIZED")
        self.call(self.command_authorize_argv(effect), error="AUTHORITY_REQUIRED")
        approval, signature, _ = self.request(self.command_authorize_argv(effect))
        self.execute_approval(approval, signature)
        self.assertEqual(self.target.read_text(), "before")
        self.execute_approval(approval, signature, error="AUTHORITY_USED")
        self.call(self.command_execute_argv(effect), error="AUTHORITY_REQUIRED")
        execution, signature, _ = self.request(self.command_execute_argv(effect))
        result = self.execute_approval(execution, signature)["result"]
        self.assertEqual(result["command_effect"]["status"], "PROCESS_COMPLETED")
        self.execute_approval(execution, signature, error="AUTHORITY_USED")
        self.assert_once()

    def test_signature_cannot_change_from_oracle_to_command_or_accept_changed_spec(self):
        self.enable()
        approval, signature, value = self.request(self.oracle_plan_argv())
        forged = deepcopy(value)
        forged["operation"]["argv"] = self.command_plan_argv()
        self.write(approval, forged)
        self.execute_approval(approval, signature, error="AUTHORITY_SIGNATURE_INVALID")
        approval, signature, _ = self.request(self.oracle_plan_argv())
        changed = json.loads(self.oracle_spec.read_text())
        changed["cases"][0]["expected"] = 999
        self.write(self.oracle_spec, changed)
        self.execute_approval(approval, signature, error="AUTHORITY_INPUT_CHANGED")
        state = self.call(["replay", "audit"])["state"]
        self.assertFalse(state.get("oracles", {}))
        self.assertEqual(self.target.read_text(), "before")

    def test_signed_command_manifest_rejects_replaced_executor_before_proposal(self):
        self.enable()
        approval, signature, _ = self.request(self.command_plan_argv())
        self.executor.write_text("raise RuntimeError('synthetic replaced command')\n")
        self.execute_approval(approval, signature, error="AUTHORITY_INPUT_CHANGED")
        self.assertEqual(self.target.read_text(), "before")
        state = self.call(["replay", "audit"])["state"]
        self.assertFalse(state.get("command_effects", {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
