"""Template admission for real ledger assets, using temporary artificial projects.

The two model roles below are deterministic protocol processes. The tests do
not establish model interpretation accuracy or independent semantic review.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_assets_v06 as asset_fixtures
import test_shared_context as handoff_fixtures
from verantyx import assets
from verantyx.domain.codec import digest
from verantyx.errors import LedgerError
from verantyx.i18n import LANGUAGES, text
from verantyx.responses import ask
from verantyx.storage.sqlite import EventStore


SOURCE = Path(__file__).resolve().parents[1] / "src"
OBSERVATIONS = {}


class FailureAssetTemplateTests(unittest.TestCase):
    def handoff_failure(self):
        fixture = handoff_fixtures.SharedContextTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        result = fixture.workflow("d['relations']=[]", max_repairs=0)
        self.assertEqual(result["state"]["editor_attempt"]["validation"]["mode"], "CROSS_VM")
        with EventStore(fixture.root, fixture.cfg["project"]["id"]) as store:
            case = next(row for row in assets.project_catalog(store, result["state"], "ja")["failure_cases"]
                        if row["family"] == "HANDOFF")
        self.assertNotIn("method_id", case)
        return fixture, result, case

    def cli(self, fixture, asset_id, locale, structured, *, output=None):
        home = fixture.root / "isolated-cli-home"
        home.mkdir(exist_ok=True)
        env = {**os.environ, "PYTHONPATH": str(SOURCE), "HOME": str(home)}
        command = [sys.executable, "-m", "verantyx", "--project", str(fixture.root), "--lang", locale]
        if structured:
            command.append("--json")
        command.extend(["asset-template", asset_id, "--claim", "next", "--target", "next.json"])
        if output:
            command.extend(["--output", output])
        return subprocess.run(command, capture_output=True, text=True, env=env, timeout=30)

    def test_handoff_is_unsupported_in_both_template_apis_without_new_events(self):
        fixture, _, case = self.handoff_failure()
        with EventStore(fixture.root, fixture.cfg["project"]["id"]) as store:
            before = store.events()
            for template in (lambda: assets.verification_template_from_asset(
                    store, case["id"], claim_id="next", target_path="next.json"),
                    lambda: assets.execution_template_from_asset(store, case["id"])):
                with self.subTest(template=template):
                    with self.assertRaises(LedgerError) as caught:
                        template()
                    self.assertEqual(caught.exception.code, "ASSET_NOT_REUSABLE")
                    self.assertEqual(caught.exception.details, {
                        "asset_id": case["id"], "kind": "FAILURE_CASE", "family": "HANDOFF",
                        "reusable_via": "handoff-editor",
                    })
            # Unsupported assets do not replace the distinct unknown-id error.
            with self.assertRaises(LedgerError) as caught:
                assets.verification_template_from_asset(store, "unknown-asset", claim_id="next", target_path="next.json")
            self.assertEqual(caught.exception.code, "ASSET_NOT_FOUND")
            self.assertEqual(store.events(), before)

    def test_handoff_cli_errors_in_five_languages_leave_ledger_and_output_untouched(self):
        fixture, result, case = self.handoff_failure()
        calls_before = fixture.fixture.calls.read_bytes()
        files_before = {path: (fixture.root / path).read_bytes() for path in ("calc.py", "test_calc.py")}
        rows = []
        with EventStore(fixture.root, fixture.cfg["project"]["id"]) as store:
            before = store.events()
            catalog_before = assets.project_catalog(store, result["state"], "ja")
        for locale in LANGUAGES:
            for structured in (True, False):
                with self.subTest(locale=locale, json=structured):
                    output = f"unsupported-{locale}-{structured}.json"
                    completed = self.cli(fixture, case["id"], locale, structured, output=output)
                    self.assertEqual(completed.returncode, 2, completed.stderr)
                    self.assertNotIn("Traceback", completed.stdout + completed.stderr)
                    self.assertNotIn("KeyError", completed.stdout + completed.stderr)
                    message = text(locale, "error.ASSET_NOT_REUSABLE")
                    if structured:
                        value = json.loads(completed.stdout)
                        self.assertEqual(value["schema_version"], 1)
                        self.assertFalse(value["ok"])
                        self.assertEqual(value["error"]["code"], "ASSET_NOT_REUSABLE")
                        self.assertEqual(value["error"]["message"], message)
                        self.assertEqual(value["error"]["details"]["family"], "HANDOFF")
                        self.assertEqual(value["error"]["details"]["reusable_via"], "handoff-editor")
                        self.assertEqual(completed.stderr, "")
                    else:
                        self.assertEqual(completed.stdout, "")
                        self.assertEqual(completed.stderr.strip(), "ASSET_NOT_REUSABLE: " + message)
                    self.assertFalse((fixture.root / output).exists())
                    with EventStore(fixture.root, fixture.cfg["project"]["id"]) as store:
                        self.assertEqual(store.events(), before)
                        self.assertEqual(assets.project_catalog(store, result["state"], "ja"), catalog_before)
                    rows.append({"locale": locale, "json": structured, "exit": completed.returncode,
                                 "message": message, "ledger_unchanged": True, "output_created": False})
        self.assertEqual(fixture.fixture.calls.read_bytes(), calls_before)
        self.assertEqual({path: (fixture.root / path).read_bytes() for path in files_before}, files_before)
        OBSERVATIONS["unsupported_cli"] = rows
        OBSERVATIONS["unsupported_ledger"] = {"events": len(before), "before_sha256": digest(before),
                                             "after_sha256": digest(before), "unchanged": True}

    def test_recorded_verification_failure_and_method_keep_the_executable_contract(self):
        fixture_factory = asset_fixtures.RecordedAssetTests(methodName="runTest")
        self.addCleanup(fixture_factory.doCleanups)
        fixture, _, result = fixture_factory.json_failure()
        projected = assets.project_assets(result["state"])
        case, method = projected["failure_cases"][0], projected["verification_methods"][0]
        rows = []
        with EventStore(fixture.root, fixture.cfg["project"]["id"]) as store:
            before = store.events()
            with mock.patch("subprocess.Popen", side_effect=AssertionError("template executed a check")):
                direct = assets.verification_template_from_asset(store, method["id"], claim_id="next", target_path="next.json")
                from_failure = assets.verification_template_from_asset(store, case["id"], claim_id="next", target_path="next.json")
            self.assertEqual(direct, from_failure)
            self.assertEqual(direct["spec"]["checks"], fixture.spec["checks"])
            self.assertEqual(direct["source_contract_hash"], digest(fixture.spec))
            self.assertFalse(direct["executed"])
            self.assertEqual(store.events(), before)
        # Both display modes still deliver a reusable spec from a failure id.
        for locale in LANGUAGES:
            for structured in (True, False):
                with self.subTest(locale=locale, json=structured):
                    completed = self.cli(fixture, case["id"], locale, structured)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stderr, "")
                    value = json.loads(completed.stdout)
                    self.assertEqual(value["template"] if structured else value, direct)
                    with EventStore(fixture.root, fixture.cfg["project"]["id"]) as store:
                        self.assertEqual(store.events(), before)
                    rows.append({"locale": locale, "json": structured, "exit": 0,
                                 "contract_unchanged": True, "ledger_unchanged": True})
        OBSERVATIONS["supported_cli"] = rows

    def test_handoff_failure_remains_a_reference_for_the_next_model(self):
        fixture, _, case = self.handoff_failure()
        adapter = fixture.fixture.adapter(filename="next-model")
        ask(fixture.root, fixture.cfg, request="Use the previous disagreement as context.",
            adapter_path=adapter, key="next-task", run_id="next-task")
        next_call = fixture.fixture.invocations()[-1]
        failures = next_call["context_assets"]["failure_cases"]
        retained = next(row for row in failures if row["id"] == case["id"])
        self.assertEqual(retained["family"], "HANDOFF")
        self.assertEqual(retained["reusable_via"], "handoff-editor")
        self.assertEqual(retained["authority"], "REFERENCE_ONLY")
        self.assertEqual(retained["enforcement"], "OFF")
        self.assertEqual(retained["prose_entailment"], "NOT_ASSESSED")
        self.assertEqual(retained["mismatch_ids"], case["mismatch_ids"])
