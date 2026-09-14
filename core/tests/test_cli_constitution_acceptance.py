"""CLI constitution acceptance using artificial projects and finite JSON checks.

Every product operation runs core/bin/verantyx in a new subprocess. The local
adapter follows the existing capture/workflow fixture protocols; it is not a
model. No product APIs, parent report APIs, Git, HTTP servers or user stores are
used. Like test_cli_processes_audit, failures include the actual CLI invocation.

Covered: attributed capture, candidate compilation, frozen negative controls,
recorded refutation, dictionary discovery, explicit second-run reuse, stale
targets, voluntary learning, and the separate command authorization gate.
Not covered: live generation, writer/worktree execution, rule revocation,
canonical adoption, authenticated consent, or independent human mastery.

Original file SHA256: not applicable (new file; absent before this addition).
"""
from pathlib import Path
import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest


CORE = Path(__file__).resolve().parents[1]
CHECKOUT = CORE.parent
QUOTE = '{"applied_count":1,"requirement":"Apply one effect for a repeated request key."}'
CHECKS = [{"id": "once", "kind": "json.equals", "pointer": "/applied_count", "expected": 1}]
CONTROLS = [{"id": "duplicate-effect", "input_base64": base64.b64encode(b'{"applied_count":2}').decode("ascii")}]

ADAPTER = r'''
import base64
import json
from pathlib import Path
import sys

request = json.load(sys.stdin)
with Path(__file__).with_name("adapter-calls.jsonl").open("a") as output:
    output.write(json.dumps(request) + "\n")
kind = request["format"]
if kind == "verantyx.proposal-request.v1":
    ref = request["external_captures"][-1]["source_ref"]
    document = request["proposal_template"]
    document["summary"] = "Check the selected retry requirement on this file."
    document["claims"] = [{"id": "retry_once", "statement": "The JSON /applied_count equals integer 1.",
                           "source_refs": [ref]}]
    document["actions"] = []
    document["unknowns"] = []
    if "decision_points" in document:
        document["decision_points"] = []
elif kind == "verantyx.asset-workflow-request.v1":
    context = request["context"]
    ref = context["external_captures"][-1]["source_ref"]
    candidate = next(row for row in context["candidates"] if row["kind"] == "VERIFICATION_IDEA")
    document = {"format": "verantyx.asset-workflow-plan.v1", "context_sha256": request["context_sha256"],
                "steps": [{"id": "retry-check", "mode": "COMPILE", "claim_id": "retry_once",
                           "target_path": "first.json", "asset_id": candidate["id"],
                           "property": "The selected JSON /applied_count equals integer 1.",
                           "method": "NEGATIVE_CONTROL",
                           "checks": [{"id": "once", "kind": "json.equals", "pointer": "/applied_count", "expected": 1}],
                           "negative_controls": [{"id": "duplicate-effect", "input_base64":
                               base64.b64encode(b'{"applied_count":2}').decode("ascii")}],
                           "expectation_basis": "The selected outside quotation explicitly contains applied_count=1.",
                           "source_refs": [ref]}], "unresolved": []}
else:
    document = request["response_template"]
    ref = request["external_captures"][-1]["source_ref"]
    document["answer"] = "The imported claim still needs a bounded check."
    document["reusable_candidates"] = [{"kind": "VERIFICATION_IDEA", "title": "Retry count check",
        "situation": "A request key is repeated", "procedure": "Check /applied_count against integer 1",
        "counterexample": "Two applied effects for the same key", "source_refs": [ref]}]
    document["learning_candidates"] = [{"concept_id": "retry_guard", "concept": "Retry guard",
        "why_now": "Review the imported requirement", "minimum_model": "One request key, one applied effect",
        "counterexample": "Two effects for one key", "check": "Explain when this finite check is insufficient",
        "source_refs": [ref]}] if request["max_learning_items"] else []
print(json.dumps(document))
'''

NETWORK_GUARD = '''
from pathlib import Path
import sys

def block_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo", "socket.sendto"):
        with Path(__file__).with_name("network-attempts.txt").open("a") as output:
            output.write(event + "\\n")
        raise RuntimeError("Network is disabled in CLI acceptance fixtures")

sys.addaudithook(block_network)
'''


class CLIConstitutionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="verantyx-cli-constitution-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.guard = self.root / "python-guard"
        self.guard.mkdir()
        (self.guard / "sitecustomize.py").write_text(NETWORK_GUARD, encoding="utf-8")
        for name in ("home", "tmp", "config", "cache", "data"):
            (self.root / name).mkdir()
        # Do not inherit credentials, user adapters, editable-package overrides,
        # or a user's HOME. Preserve only the explicitly supplied local engine.
        self.environment = {
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.defpath,
            "HOME": str(self.root / "home"), "TMPDIR": str(self.root / "tmp"),
            "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_CACHE_HOME": str(self.root / "cache"),
            "XDG_DATA_HOME": str(self.root / "data"), "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0", "PYTHONUTF8": "1", "NO_COLOR": "1", "TERM": "dumb",
            "PYTHONPATH": os.pathsep.join(str(path) for path in (CORE / "src", CORE / "tests", self.guard)),
            "VERANTYX_PRECEDENT": str(CHECKOUT / "execution"),
        }
        if "VERANTYX_CROSS" in os.environ:
            self.environment["VERANTYX_CROSS"] = os.environ["VERANTYX_CROSS"]
        self.base = [sys.executable, str(CORE / "bin" / "verantyx"), "--project", str(self.root), "--lang", "en", "--json"]
        self.adapter = self.root / "adapter.json"
        self.script = self.root / "adapter.py"
        self.script.write_text(ADAPTER, encoding="utf-8")
        self.write_json(self.adapter, {"argv": [sys.executable, str(self.script)]})
        self.cli("setup", "--non-interactive", "--name", "Artificial CLI constitution acceptance",
                 "--learning", "manual", "--max-items", "3")

    def write_json(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def cli(self, *args, ok=True, error=None):
        argv = [*self.base, *map(str, args)]
        process = subprocess.run(argv, cwd=self.root, env=self.environment,
                                 capture_output=True, text=True, timeout=15)
        detail = shlex.join(argv) + "\nexit=" + str(process.returncode) + "\n" + process.stdout[:4000] + process.stderr[:4000]
        self.assertFalse((self.guard / "network-attempts.txt").exists(), detail)
        self.assertNotIn("Traceback", process.stderr, detail)
        try:
            value = json.loads(process.stdout)
        except ValueError:
            self.fail(detail)
        if error is not None:
            self.assertNotEqual(process.returncode, 0, detail)
            self.assertEqual(value["error"]["code"], error, detail)
        else:
            self.assertNotIn("error", value, detail)
            self.assertEqual(value.get("ok", True), ok, detail)
            # The CLI exits 4 for a recorded negative or unknown domain result.
            self.assertEqual(process.returncode, 0 if ok else 4, detail)
        return value

    def invocations(self):
        path = self.root / "adapter-calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def start(self, run_id, target, count, *extra_observations):
        self.write_json(target, {"applied_count": count})
        observed = [argument for name in (target, *extra_observations) for argument in ("--observe", name)]
        return self.cli("run", "Check the selected JSON /applied_count equals integer 1.", "--task-id", run_id,
                        "--component", "retry-fixture", "--workload", "finite-json", "--risk", "LOW", *observed)

    def bind(self, run_id, target, count):
        first = self.start(run_id, target, count)
        proposal = self.write_json(run_id + "-proposal.json", {
            "schema_version": 1, "task_id": run_id, "context_revision": first["state"]["revision"],
            "response_locale": "en", "summary": "Artificial current-run claim",
            "claims": [{"id": "retry_once", "statement": "The JSON /applied_count equals integer 1.",
                        "source_refs": [first["state"]["latest_observations"][target]]}],
            "actions": [], "unknowns": [],
        })
        return self.cli("resume", run_id, "--proposal", proposal, "--key", run_id + "-proposal")

    def captured(self, *extra_observations):
        first = self.start("first", "first.json", 2, *extra_observations)
        quote = self.root / "outside-response.json"
        quote.write_text(QUOTE, encoding="utf-8")
        result = self.cli("capture", "first", "--input", quote, "--format", "json", "--provider", "synthetic-outside",
                          "--model", "fixture-model", "--source-label", "Selected retry answer", "--key", "capture",
                          "--expected-revision", first["recorded_revision"], "--adapter", self.adapter,
                          "--include", "first.json", "--timeout", "5")
        self.assertEqual(result["collection_mode"], "PROPOSAL_AND_RESPONSE")
        self.assertEqual(len(self.invocations()), 2)
        self.assertEqual(result["state"]["latest_response"]["mode"], "GENERATED")
        return result

    def checked(self, captured):
        result = self.cli("asset-loop", "first", "--adapter", self.adapter, "--key", "compile-check",
                          "--expected-revision", captured["recorded_revision"], "--include", "first.json",
                          "--timeout", "5", "--max-rounds", "1", "--max-checks", "1", ok=False)
        self.assertEqual(result["workflow"]["status"], "REFUTED")
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(len(self.invocations()), 3)
        return result

    def method(self, catalog, run_id):
        rows = [row for row in catalog["verification_methods"] if row["owner_run"] == run_id]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def assert_no_authority(self, state):
        self.assertFalse(state["can_execute_effects"])
        self.assertEqual(state["human_decisions"], {})
        for key in ("effects", "adoptions", "rules"):
            self.assertFalse(state.get(key, {}), key)
        self.assertEqual(state["assessment"]["mastery_evidence"], "NONE")

    def test_capture_failure_dictionary_and_explicit_second_run_reuse(self):
        captured = self.captured()
        quoted = captured["state"]["external_captures"][0]
        self.assertEqual(quoted["body"], QUOTE)
        self.assertEqual(quoted["body_sha256"], hashlib.sha256(QUOTE.encode()).hexdigest())
        self.assertEqual(quoted["source_ref"], captured["capture_source_ref"])
        self.assertEqual(quoted["provenance"], {
            "transport": "EXPLICIT_IMPORT", "provider": "synthetic-outside", "model": "fixture-model",
            "source_label": "Selected retry answer", "attribution": "USER_SUPPLIED_UNVERIFIED",
        })
        self.assertEqual(quoted["claims_status"], "UNVERIFIED")
        self.assertEqual(quoted["authority"], "REFERENCE_ONLY")
        self.assert_no_authority(captured["state"])
        failed = self.checked(captured)
        step = failed["workflow"]["plan"]["steps"][0]
        self.assertEqual(step["mode"], "COMPILE")
        self.assertEqual(step["source_refs"], [quoted["source_ref"]])
        self.assertIn(quoted["source_ref"], json.dumps(step["expectation_bindings"]))
        self.assertEqual(step["expectation_origin"], "MODEL_PROPOSED")
        self.assertEqual(step["spec"]["checks"], CHECKS)
        self.assertEqual(step["spec"]["negative_controls"], CONTROLS)
        verification = next(iter(failed["state"]["verifications"].values()))
        evidence = verification["receipt"]["result"]
        self.assertEqual(evidence["closure"], "REFUTED")
        self.assertEqual(evidence["checks"][0]["actual_hash"], hashlib.sha256(b"2").hexdigest())
        self.assertFalse(evidence["checks"][0]["passed"])
        self.assertTrue(evidence["negative_controls"][0]["rejected"])
        self.assert_no_authority(failed["state"])
        catalog = self.cli("dictionary", "applied_count", "--run", "first")["catalog"]
        original = self.method(catalog, "first")
        failure = next(row for row in catalog["failure_cases"] if row["owner_run"] == "first")
        self.assertEqual(failure["method_id"], original["id"])
        self.assertEqual(failure["case_kind"], "REFUTATION")
        self.assertEqual(failure["checks"][0]["expected"], 1)
        self.assertEqual(failure["checks"][0]["observed"], 2)
        self.assertTrue(failure["source_refs"])
        self.assertEqual(catalog["authority"], "REFERENCE_ONLY")
        requests = self.invocations()
        self.assertEqual(requests[-1]["context"]["external_captures"], [quoted])
        self.assertEqual([request["external_captures"] for request in requests[:2]], [[quoted], [quoted]])

        # This is a separately recorded run and proposal, with no adapter call.
        second = self.bind("second", "second.json", 1)
        self.adapter.unlink()
        self.script.unlink()
        arguments = ("asset-loop", "second", "--asset", original["id"], "--claim", "retry_once", "--target", "second.json",
                     "--expected-revision", second["recorded_revision"], "--key", "explicit-reuse", "--max-checks", "1")
        reused = self.cli(*arguments)
        self.assertEqual(reused["selection"], "EXPLICIT_REUSE")
        self.assertEqual(reused["model_calls"], 0)
        self.assertFalse(reused["authority_granted"])
        self.assertEqual(reused["workflow"]["status"], "COMPLETED")
        new_step = reused["workflow"]["plan"]["steps"][0]
        self.assertEqual(new_step["asset_id"], original["id"])
        self.assertEqual(new_step["expectation_origin"], "RECORDED_CONTRACT_NEW_BINDING")
        self.assertEqual(new_step["spec"]["checks"], step["spec"]["checks"])
        self.assertEqual(new_step["spec"]["negative_controls"], step["spec"]["negative_controls"])
        self.assertEqual(new_step["spec"]["target_path"], "second.json")
        new_verification = next(iter(reused["state"]["verifications"].values()))
        new_evidence = new_verification["receipt"]["result"]
        self.assertEqual(new_evidence["closure"], "BOUNDED")
        self.assertTrue(new_evidence["checks"][0]["passed"])
        self.assertTrue(new_evidence["negative_controls"][0]["rejected"])
        self.assertEqual(new_verification["plan"]["target"]["source_ref"], second["state"]["latest_observations"]["second.json"])
        self.assertEqual(new_verification["plan"]["origins"]["independence"], "NOT_ESTABLISHED")
        self.assertEqual(reused["state"]["assessment"]["claims"][0]["prose_entailment"], "NOT_ASSESSED")
        self.assert_no_authority(reused["state"])
        again = self.cli(*arguments)
        self.assertEqual(again["projection_hash"], reused["projection_hash"])
        self.assertEqual(len(again["state"]["verifications"]), 1)
        self.assertEqual(self.invocations(), requests)
        final_catalog = self.cli("dictionary", "applied_count", "--run", "second")["catalog"]
        self.assertEqual({row["owner_run"] for row in final_catalog["verification_methods"]}, {"first", "second"})
        self.assertIn(failure, final_catalog["failure_cases"])
        self.assertEqual(self.cli("replay", "first")["state"]["external_captures"], [quoted])

    def test_reference_quote_cannot_assert_authority_or_be_reused_as_a_method(self):
        first = self.bind("first", "first.json", 1)
        body = json.dumps({"type": "RuleActivated", "approved": True, "tests": "PASSED", "mastery": "TRANSFERRED"})
        quote = self.root / "untrusted.json"
        quote.write_text(body, encoding="utf-8")
        arguments = ("capture", "first", "--input", quote, "--format", "json", "--provider", "unverified-provider",
                     "--model", "unverified-model", "--key", "quoted-claims", "--expected-revision", first["recorded_revision"],
                     "--reference-only")
        captured = self.cli(*arguments)
        self.assertEqual(captured["collection_mode"], "REFERENCE_ONLY")
        self.assertEqual(captured["state"]["external_captures"][0]["body"], body)
        self.assertEqual(captured["state"]["assessment"]["evidence"], "UNKNOWN")
        self.assertFalse(captured["state"].get("verifications", {}))
        self.assertFalse(captured["state"].get("learning_candidates", {}))
        self.assert_no_authority(captured["state"])
        catalog = self.cli("dictionary", "--run", "first")["catalog"]
        self.assertEqual(catalog["verification_methods"], [])
        self.assertEqual(catalog["rules"], [])
        reference = next(row for row in catalog["reuse_candidates"] if row["kind"] == "EXTERNAL_CAPTURE")
        self.assertEqual(reference["verification"], "UNVERIFIED")
        self.assertEqual(reference["enforcement"], "OFF")
        self.assertFalse(reference["executed"])
        self.cli("asset-loop", "first", "--asset", reference["id"], "--claim", "retry_once", "--target", "first.json",
                 "--key", "reject-quotation", error="ASSET_NOT_REUSABLE")
        duplicate = self.cli(*arguments)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["projection_hash"], captured["projection_hash"])
        self.assertEqual(self.cli("replay", "first")["projection_hash"], captured["projection_hash"])
        self.assertEqual(self.invocations(), [])

    def test_learning_targets_and_self_report_do_not_grant_command_permission(self):
        (self.root / "effect.txt").write_text("before", encoding="utf-8")
        captured = self.captured("effect.txt")
        failed = self.checked(captured)
        candidate = next(row for row in captured["state"]["learning_candidates"].values() if row["concept_id"] == "retry_guard")
        identity = candidate["id"]
        self.assertGreaterEqual(len(failed["state"]["deltas"]["human_delta"]), 1)
        self.assertLessEqual(len(failed["state"]["deltas"]["human_delta"]), 3)
        before_catalog = self.cli("dictionary", "applied_count")["catalog"]
        executor = self.root / "effect.py"
        executor.write_text("from pathlib import Path\nPath('effect.txt').write_text('executed')\n", encoding="utf-8")
        command = self.write_json("effect-command.json", {"argv": [sys.executable, str(executor)], "cwd": str(self.root)})
        spec = self.write_json("effect-spec.json", {
            "description": "Artificial reversible local effect", "effect_class": "REVERSIBLE_LOCAL", "targets": ["effect.txt"],
            "external_target": "", "input": {}, "timeout": 2, "max_output": 4096, "dependencies": [],
            "compensation": "Restore the artificial fixture",
        })
        proposed = self.cli("command-propose", "first", "--spec", spec, "--command-file", command, "--key", "effect-proposal")
        for target in ("OWN", "REVIEW", "REFERENCE", "DELEGATE"):
            with self.subTest(target=target):
                selected = self.cli("learn-target", "first", "--candidate", identity, "--target", target,
                                    "--reason", "Artificial voluntary choice", "--key", "target-" + target.lower())
                row = next(row for row in selected["candidates"] if row["id"] == identity)
                self.assertEqual(row["ownership_target"], target)
                self.assertFalse(row["target_is_suggestion"])
                self.assertEqual(row["mastery_evidence"], "NONE")
                self.assertEqual(row["mastery_assessment"], "NOT_ASSESSED")
                self.assertFalse(row["externally_verified"])
                self.assertEqual(row["evidence"], [])
                self.assert_no_authority(selected["state"])
        self.cli("command-execute", "first", "--effect", proposed["command_effect_id"], "--command-file", command,
                 "--key", "delegate-is-not-permission", error="COMMAND_NOT_AUTHORIZED")
        self.assertEqual((self.root / "effect.txt").read_text(), "before")
        report = self.cli("learn-explain", "first", "--candidate", identity, "--statement", "Artificial self report of understanding",
                          "--key", "self-report")
        row = next(row for row in report["candidates"] if row["id"] == identity)
        self.assertEqual(row["ownership_target"], "DELEGATE")
        self.assertEqual(row["mastery_evidence"], "SELF_REPORTED")
        self.assertEqual(row["mastery_assessment"], "NOT_ASSESSED")
        self.assertFalse(row["externally_verified"])
        self.assert_no_authority(report["state"])
        catalog = self.cli("dictionary", "retry_guard")["catalog"]
        learning = next(row for row in catalog["learning"] if row["id"] == identity)
        self.assertEqual(learning["ownership_target"], "DELEGATE")
        self.assertEqual(learning["mastery_assessment"], "NOT_ASSESSED")
        self.assertEqual(catalog["rules"], [])
        self.cli("learn-defer", "first", "--candidate", identity, "--reason", "Continue the artificial task first", "--key", "defer")
        default_catalog = self.cli("dictionary")["catalog"]
        self.assertNotIn(identity, [row["id"] for row in default_catalog["learning"]])
        retained = self.cli("dictionary", "applied_count")["catalog"]
        self.assertEqual(retained["verification_methods"], before_catalog["verification_methods"])
        self.assertEqual(retained["failure_cases"], before_catalog["failure_cases"])
        self.assertEqual(len(self.invocations()), 3)

    def test_reuse_requires_current_scope_and_changed_target_records_unknown(self):
        self.checked(self.captured())
        original = self.method(self.cli("dictionary", "applied_count")["catalog"], "first")
        second = self.bind("second", "second.json", 1)
        self.adapter.unlink()
        self.script.unlink()
        arguments = ("asset-loop", "second", "--asset", original["id"], "--claim", "retry_once")
        self.cli(*arguments, "--target", "first.json", "--key", "outside-scope", error="PATH_SCOPE")
        self.cli(*arguments, "--target", "second.json", "--key", "old-revision", "--expected-revision",
                 second["recorded_revision"] - 1, error="REVISION_CONFLICT")
        self.assertEqual(self.cli("replay", "second")["projection_hash"], second["projection_hash"])
        preview = self.cli(*arguments, "--target", "second.json", "--key", "preview", "--preview")
        self.assertEqual(preview["workflow"]["status"], "PLANNED")
        self.assertEqual(preview["model_calls"], 0)
        self.assertFalse(preview["state"].get("verifications", {}))
        spec = self.write_json("rebound-check.json", preview["workflow"]["plan"]["steps"][0]["spec"])
        planned = self.cli("verify-plan", "second", "--spec", spec, "--key", "freeze-before-change")
        self.write_json("second.json", {"applied_count": 2})
        invalidated = self.cli("verify-run", "second", "--verification", planned["verification_id"], "--key", "changed-target", ok=False)
        self.assertEqual(invalidated["verification"]["receipt"]["reason"], "TARGET_CHANGED")
        self.assertIsNone(invalidated["verification"]["receipt"]["result"])
        catalog = self.cli("dictionary", "--run", "second")["catalog"]
        unknown = next(row for row in catalog["failure_cases"] if row["owner_run"] == "second")
        self.assertEqual(unknown["case_kind"], "UNRESOLVED_EXECUTION")
        # Invalidation records no verifier result, hence no evidence closure.
        self.assertIsNone(unknown["closure"])
        self.assertEqual(unknown["checks"], [])
        self.assertEqual(unknown["reason"], "TARGET_CHANGED")
        self.assert_no_authority(invalidated["state"])
        self.assertEqual(len(self.invocations()), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
