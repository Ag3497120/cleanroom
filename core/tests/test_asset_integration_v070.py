"""Real CLI and HTTP paths for experience capture and subsequent file checks."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
import contextlib
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest

from verantyx import config
from verantyx.cli import main
from verantyx.i18n import LANGUAGES, text
from verantyx.model_api import FORMAT

SOURCE = Path(__file__).resolve().parents[1] / "src"


def document(value, mode="normal"):
    if value["format"] == "verantyx.proposal-request.v1":
        result = deepcopy(value["proposal_template"])
        result.update(summary="Check the selected result against the selected requirement.", actions=[], unknowns=[], decision_points=[])
        result["claims"] = [{"id": "claim-property", "statement": "The selected result satisfies the selected requirement.",
                             "source_refs": [value["task"]["source_ref"]]}]
        return result
    if value["format"] == "verantyx.asset-workflow-request.v1":
        context = value["context"]
        target = next(row for row in context["selected_files"] if row["path"].endswith("result.json"))
        source = next(row for row in context["selected_files"] if row["path"] == "requirements.json")
        requirement = json.loads(source["text"])
        methods = context["available_methods"]
        step = {"id": "check-property", "mode": "REUSE" if methods else "COMPILE",
                "claim_id": context["claims"][0]["id"], "target_path": target["path"],
                "asset_id": methods[0]["id"] if methods else None,
                "property": None if methods else "The recorded counter equals the required value.",
                "method": None if methods else "TEST",
                "checks": [] if methods else [{"id": "count", "kind": "json.equals", "pointer": "/count", "expected": requirement["expected"]}],
                "negative_controls": [], "expectation_basis": "Selected requirement document.",
                "source_refs": [source["source_ref"], methods[0]["source_ref"] if methods else context["request_ref"]]}
        if mode == "bad-plan":
            step["target_path"] = "unselected-private.json"
        return {"format": "verantyx.asset-workflow-plan.v1", "context_sha256": value["context_sha256"],
                "steps": [step], "unresolved": []}
    result = deepcopy(value["response_template"])
    outcome = value.get("asset_workflow", {}).get("status", "NO_CHECK_REQUESTED")
    result["answer"] = "Recorded checking outcome: " + outcome
    refs = value.get("asset_workflow", {}).get("source_refs") or [value["task"]["source_ref"]]
    result["reusable_candidates"] = [{"kind": "VERIFICATION_IDEA", "title": "Compare the recorded count",
        "situation": "The result must match a separate requirement.", "procedure": "Reuse the fixed count check.",
        "counterexample": "Do not change the expected count to fit a failed result.", "source_refs": refs[:1]}]
    result["learning_candidates"] = []
    if value["max_learning_items"]:
        result["learning_candidates"] = [{"concept_id": "fixed_expectation", "concept": "Preserving expectations",
            "why_now": "A result was checked against a requirement.", "minimum_model": "Keep the expected value fixed.",
            "counterexample": "Accepting a different value after failure.", "check": "Explain what this one check establishes.",
            "source_refs": refs[:1]}]
    return result


class AssetIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        (self.root / "requirements.json").write_text('{"expected":1}')
        (self.root / "old-result.json").write_text('{"count":2}')
        (self.root / "new-result.json").write_text('{"count":1}')
        self.calls = self.root / "calls.jsonl"
        self.adapter = self.make_adapter()

    def make_adapter(self, mode="normal"):
        path = self.root / (mode + ".py")
        path.write_text("from copy import deepcopy\nimport json,sys\nfrom pathlib import Path\n" + inspect.getsource(document)
                        + "\nv=json.load(sys.stdin)\n"
                        + f"with Path({str(self.calls)!r}).open('a') as f:f.write(json.dumps(v)+'\\n')\n"
                        + f"print(json.dumps(document(v,{mode!r})))\n")
        adapter = self.root / (mode + ".json")
        adapter.write_text(json.dumps({"argv": [sys.executable, str(path)]}))
        return adapter

    def invocations(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def cli(self, *args, expected=0):
        env = dict(os.environ, PYTHONPATH=str(SOURCE), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(self.root), "--json", *map(str, args)],
                                env=env, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def ask(self, name, target, *extra, adapter=None):
        return self.cli("ask", "Check the count against requirements.json", "--task-id", name, "--key", name,
                        "--adapter", adapter or self.adapter, "--include", target, "--include", "requirements.json", *extra)

    def test_first_failure_becomes_next_task_frozen_check_and_answer_evidence(self):
        first = self.ask("first", "old-result.json", "--auto-check")
        self.assertFalse(first["checks_ok"])
        self.assertEqual(first["asset_workflow"]["status"], "REFUTED")
        self.assertIn("REFUTED", first["state"]["latest_response"]["document"]["answer"])
        self.assertTrue(first["state"]["deltas"]["system_delta"]["failure_assets"])
        second = self.ask("second", "new-result.json", "--auto-check")
        self.assertTrue(second["checks_ok"])
        step = second["asset_workflow"]["plan"]["steps"][0]
        self.assertEqual(step["mode"], "REUSE")
        self.assertEqual(step["spec"]["checks"], first["asset_workflow"]["plan"]["steps"][0]["spec"]["checks"])
        self.assertEqual(second["asset_workflow"]["results"][0]["closure"], "BOUNDED")
        self.assertEqual(second["state"]["effects"], {})
        self.assertEqual(second["state"]["human_decisions"], {})
        self.assertTrue(all(item["mastery_assessment"] == "NOT_ASSESSED" for item in second["state"]["deltas"]["human_delta"]))
        count = len(self.invocations())
        duplicate = self.ask("second", "new-result.json", "--auto-check")
        self.assertEqual(len(self.invocations()), count)
        self.assertEqual(duplicate["projection_hash"], second["projection_hash"])

    def test_invalid_plans_remain_visible_without_false_verification(self):
        result = self.ask("bad", "old-result.json", "--auto-check", adapter=self.make_adapter("bad-plan"))
        self.assertFalse(result["checks_ok"])
        self.assertEqual(result["asset_workflow"]["status"], "NO_PLAN")
        self.assertEqual(result["state"].get("verifications", {}), {})
        response_input = self.invocations()[-1]
        self.assertEqual(response_input["asset_workflow"]["status"], "NO_PLAN")
        self.assertIn("PLANNING_REJECTED", response_input["asset_workflow"]["unresolved"])
        self.assertEqual(len([v for v in self.invocations() if v["format"] == "verantyx.asset-workflow-request.v1"]), 2)

    def test_disabled_checks_keep_existing_two_calls(self):
        result = self.ask("ordinary", "old-result.json")
        self.assertEqual(len(self.invocations()), 2)
        self.assertNotIn("asset_workflows", result["state"])
        self.assertNotIn("checks_ok", result)

    def test_standalone_propose_collect_is_resumable(self):
        base = self.cli("run", "Review the result", "--task-id", "collect", "--observe", "old-result.json")
        args = ("propose", "collect", "--adapter", self.adapter, "--key", "collect", "--expected-revision",
                base["recorded_revision"], "--collect", "--include", "old-result.json")
        result = self.cli(*args)
        self.assertTrue(result["collected"])
        self.assertTrue(result["state"]["deltas"]["system_delta"]["reuse_candidates"])
        self.assertEqual(len(self.invocations()), 2)
        self.assertEqual(self.cli(*args)["projection_hash"], result["projection_hash"])
        self.assertEqual(len(self.invocations()), 2)

    def test_console_toggle_runs_checks_and_displays_recorded_failure(self):
        class Terminal(io.StringIO):
            def isatty(self):
                return True
        output = Terminal()
        with mock.patch("sys.stdin", Terminal("/checks on\nCheck the count\n/checks off\n/quit\n")), contextlib.redirect_stdout(output):
            code = main(["--project", str(self.root), "--lang", "ja", "start", "--plain", "--adapter", str(self.adapter),
                         "--include", "old-result.json", "--include", "requirements.json"])
        self.assertEqual(code, 0)
        self.assertIn(text("ja", "workflow.status.REFUTED"), output.getvalue())
        self.assertIn(text("ja", "console.checks.off"), output.getvalue())
        self.assertEqual(len(self.invocations()), 3)

    def test_local_http_model_adapter_accepts_new_planning_protocol(self):
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                value = json.loads(body["prompt"])
                calls.append((value, body["format"]))
                raw = json.dumps({"done": True, "done_reason": "stop", "response": json.dumps(document(value))}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown();server.server_close();thread.join(timeout=3)
        self.addCleanup(cleanup)
        adapter = self.root / "http-model.json"
        adapter.write_text(json.dumps({"format": FORMAT, "provider": "ollama", "model": "synthetic",
            "endpoint": f"http://127.0.0.1:{server.server_port}/api/generate", "key_env": None,
            "allow_loopback_http": True, "timeout": 30, "max_output_tokens": 8192, "max_response_bytes": 262144}))
        result = self.ask("http", "new-result.json", "--auto-check", adapter=adapter)
        self.assertTrue(result["checks_ok"])
        self.assertEqual(len(calls), 3)
        plan_request, schema = calls[1]
        self.assertEqual(plan_request["format"], "verantyx.asset-workflow-request.v1")
        self.assertEqual(schema["properties"]["format"]["const"], "verantyx.asset-workflow-plan.v1")

    def test_all_locales_have_workflow_outcomes_and_command_help(self):
        for locale in LANGUAGES:
            for status in ("COMPLETED", "REFUTED", "NO_PLAN", "PLANNED", "INVALIDATED", "OUTCOME_UNKNOWN", "CONTESTED"):
                self.assertNotEqual(text(locale, "workflow.status." + status), "workflow.status." + status)
            help_result = self.cli("--lang", locale, "--help")
            self.assertIn("asset-loop", json.dumps(help_result, ensure_ascii=False))
            self.assertIn("capture", json.dumps(help_result, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
