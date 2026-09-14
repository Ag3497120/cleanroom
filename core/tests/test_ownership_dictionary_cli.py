"""Frozen artificial CLI cases; no real project, model, network or authority."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

from verantyx import config
from verantyx.application import iso, record_run
from verantyx.assets import project_catalog
from verantyx.cli import main, parse
from verantyx.commands_response import display
from verantyx.domain.codec import canonical, digest
from verantyx.domain.events import make_event
from verantyx.learning import control_learning
from verantyx.ownership_dictionary import LABELS, PLACEMENT, project_ownership_dictionary
from verantyx.storage.sqlite import EventStore


class OwnershipDictionaryCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="verantyx-ownership-fixture-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cfg = config.defaults(self.root, "en")
        self.cfg["learning"]["max_items"] = 1
        config.save(self.root, self.cfg, None)
        self.clock = lambda: datetime(2026, 9, 10, tzinfo=timezone.utc)
        self.starts = {}
        self.start("first")
        self.environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                            "PYTHONPATH": os.pathsep.join((str(Path(__file__).resolve().parents[1] / "src"),
                                                         str(Path(__file__).resolve().parent)))}

    def start(self, run_id):
        self.starts[run_id] = record_run(self.root, self.cfg, request="Artificial ownership fixture", run_id=run_id,
                                         clock=self.clock)["state"]

    def raise_item(self, name, target=None, *, run_id="first", concept=None):
        raised = control_learning(self.root, self.cfg, run_id, "raise", concept_id=name,
                                  concept=concept or "Fixture " + name, why_now="A bounded artificial case",
                                  minimum_model="Check scope before reuse", counterexample="A changed precondition",
                                  check="Name the current scope", source_refs=[self.starts[run_id]["request_ref"]],
                                  clock=self.clock)
        identity = raised["candidate_id"]
        if target:
            self.select(identity, target, run_id=run_id)
        return identity

    def select(self, identity, target, *, run_id="first"):
        result = control_learning(self.root, self.cfg, run_id, "target", candidate_id=identity, target=target,
                                  reason="Synthetic operator choice", clock=self.clock)
        return result["state"]["learning_candidates"][identity]["target_ref"]

    def call(self, *args, text=False, locale="en", error=None):
        process = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(self.root), "--lang", locale,
                                  *([] if text else ["--json"]), "dictionary", *args], cwd=self.root,
                                 env=self.environment, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.stderr, "", process.stdout + process.stderr)
        if error:
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(json.loads(process.stdout)["error"]["code"], error)
            return
        self.assertEqual(process.returncode, 0, process.stdout)
        return process.stdout if text else json.loads(process.stdout)["catalog"]

    def test_default_all_preserves_catalog_and_free_text_query(self):
        self.raise_item("alpha", "OWN")
        self.raise_item("beta", "DELEGATE")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            expected = project_catalog(store, None, "en")
        self.assertEqual(self.call(), expected)
        self.assertEqual(self.call("--view", "all"), expected)
        self.assertEqual(len(expected["learning"]), 1)
        self.assertEqual(self.call("Fixture beta"), self.call("Fixture beta", "--view", "all"))
        _, args = parse(["dictionary", "Fixture beta", "--view", "delegate"])
        self.assertEqual((args.query, args.view), ("Fixture beta", "delegate"))

    def test_full_history_is_split_after_explicit_selection_not_short_delta(self):
        owned = {self.raise_item("owned-" + str(index), "OWN") for index in range(6)}
        review = self.raise_item("review", "REVIEW")
        reference = self.raise_item("reference", "REFERENCE")
        delegate = self.raise_item("delegate", "DELEGATE")
        suggestion = self.raise_item("undecided")
        learned = self.call("--view", "learn")
        by_id = {row["id"]: row for row in learned["learning"]}
        self.assertEqual(set(by_id), owned | {review, reference, suggestion})
        self.assertEqual(by_id[review]["selected_target"], "REVIEW")
        self.assertEqual(by_id[reference]["selected_target"], "REFERENCE")
        self.assertIsNone(by_id[suggestion]["selected_target"])
        self.assertEqual(by_id[suggestion]["selection_status"], "SUGGESTED")
        delegated = self.call("--view", "delegate")
        self.assertEqual([row["id"] for row in delegated["learning"]], [delegate])
        self.assertEqual(delegated["learning"][0]["selection_status"], "HUMAN_SELECTED")
        self.assertEqual(delegated["ownership"]["placement"], PLACEMENT)
        for flag in ("delegation_grants_authority", "delegation_proves_mastery", "automatic_activation",
                     "lookup_resumes_learning", "system_references_are_selected_delegations"):
            self.assertFalse(delegated["ownership"][flag])
        self.assertTrue(delegated["ownership"]["learning_voluntary"])
        self.assertEqual(delegated["learning"][0]["mastery_assessment"], "NOT_ASSESSED")
        self.assertEqual(delegated["learning"][0]["authority"], "REFERENCE_ONLY")

    def test_latest_target_change_moves_item_and_preserves_citations(self):
        identity = self.raise_item("changing", "OWN")
        first = self.call("--view", "learn")["learning"][0]
        for target in ("DELEGATE", "REVIEW", "REFERENCE", "OWN"):
            target_ref = self.select(identity, target)
            view = PLACEMENT[target]
            found = self.call(identity, "--view", view)["learning"]
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["ownership_target"], target)
            self.assertEqual(found[0]["selected_target"], target)
            self.assertEqual(found[0]["target_ref"], target_ref)
            self.assertEqual(found[0]["source_refs"], first["source_refs"])
            self.assertEqual(found[0]["source_ref"], first["source_ref"])
            other = "learn" if view == "delegate" else "delegate"
            self.assertEqual(self.call(identity, "--view", other)["learning"], [])

    def test_suggested_delegate_is_not_a_human_selected_delegation(self):
        anchor = self.starts["first"]["request_ref"]
        payload = {"id": "suggested-delegate", "concept_id": "suggested-delegate", "concept": "Undecided delegation",
                   "why_now": ["Synthetic suggestion"], "project_anchor": anchor, "source_refs": [anchor],
                   "suggested_target": "DELEGATE", "minimum_model": "Keep authority separate",
                   "counterexample": "A suggestion treated as permission", "check": "Identify the missing choice",
                   "system_capture": ["REFERENCE"], "origin": "LOCAL"}
        with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
            previous = store.events("first")
            command = str(uuid.uuid4())
            raised = make_event(store.project_id, "first", len(previous) + 1, command, iso(self.clock()),
                                "LearningCandidateRaised", payload, str(uuid.uuid4()), previous[-1])
            evaluated = make_event(store.project_id, "first", len(previous) + 2, command, iso(self.clock()),
                                   "EvaluationRecorded", {"as_of": iso(self.clock()), "evaluator": "m1.v1"},
                                   str(uuid.uuid4()), raised)
            store.append("synthetic-suggestion", digest(payload), "first", len(previous), [raised, evaluated])
        self.assertEqual(self.call("--view", "delegate")["learning"], [])
        row = self.call("--view", "learn")["learning"][0]
        self.assertEqual(row["ownership_target"], "DELEGATE")
        self.assertIsNone(row["selected_target"])
        self.assertTrue(row["target_is_suggestion"])
        self.assertEqual(row["selection_status"], "SUGGESTED")

    def test_cross_run_query_limit_and_context_ranking(self):
        self.raise_item("old", "OWN", concept="Shared Needle old")
        self.start("second")
        newest = self.raise_item("new", "OWN", run_id="second", concept="Shared Needle new")
        result = self.call("sHaReD nEeDlE", "--view", "learn", "--run", "second", "--limit", "1")
        self.assertEqual([row["id"] for row in result["learning"]], [newest])
        self.assertEqual(result["truncated"]["learning"], 1)
        result = self.call("shared needle", "--view", "learn", "--run", "second", "--limit", "2")
        self.assertEqual({row["owner_run"] for row in result["learning"]}, {"first", "second"})
        self.assertEqual(result["truncated"]["learning"], 0)
        self.assertEqual(self.call("absent token", "--view", "learn")["learning"], [])

    def test_off_and_deferred_saved_choices_are_visible_without_resuming(self):
        self.cfg["learning"]["mode"] = "off"
        self.start("off")
        for target in ("OWN", "DELEGATE"):
            identity = self.raise_item("off-" + target, target, run_id="off")
            control_learning(self.root, self.cfg, "off", "defer", candidate_id=identity,
                             reason="Learning remains voluntary", clock=self.clock)
            row = self.call(identity, "--view", PLACEMENT[target])["learning"][0]
            self.assertEqual(row["status"], "DEFERRED")
            self.assertEqual(row["selected_target"], target)
            self.assertTrue(row["learning_voluntary"])
        self.assertEqual(self.call()["learning"], [])

    def test_lookup_has_no_model_process_network_or_ledger_mutation(self):
        identity = self.raise_item("private", "DELEGATE")
        control_learning(self.root, self.cfg, "first", "explain", candidate_id=identity,
                         statement="PRIVATE_SELF_REPORT_MARKER", clock=self.clock)
        # The existing command gate bootstraps an empty coordination lock on
        # first CLI use. Establish that fixture before comparing stored bytes.
        self.call("--view", "all")
        before = {str(path.relative_to(self.root)): sha256(path.read_bytes()).hexdigest()
                  for path in self.root.rglob("*") if path.is_file()}
        with mock.patch("socket.socket", side_effect=AssertionError("network")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("subprocess.Popen", side_effect=AssertionError("process")), \
             mock.patch("verantyx.responses.ask", side_effect=AssertionError("model")), \
             mock.patch("verantyx.responses.compose", side_effect=AssertionError("model")), \
             mock.patch.object(EventStore, "append", side_effect=AssertionError("ledger write")):
            for view in ("all", "learn", "delegate"):
                for output_args in ([], ["--json"]):
                    output = StringIO()
                    with redirect_stdout(output):
                        code = main(["--project", str(self.root), "--lang", "en", *output_args,
                                     "dictionary", "--view", view])
                    self.assertEqual(code, 0, output.getvalue())
                    self.assertNotIn("PRIVATE_SELF_REPORT_MARKER", output.getvalue())
        after = {str(path.relative_to(self.root)): sha256(path.read_bytes()).hexdigest()
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_text_exposes_targets_boundaries_and_safe_controls_in_five_locales(self):
        for target in PLACEMENT:
            self.raise_item("text-" + target, target, concept="Fixture " + target + "\x1b[31m\u202e")
        for locale in LABELS:
            for view in ("all", "learn", "delegate"):
                output = self.call("--view", view, text=True, locale=locale)
                self.assertIn(LABELS[locale]["boundary"], output)
                self.assertNotIn("\x1b", output)
                self.assertNotIn("\u202e", output)
                self.assertIn("\\u001b", output)
                self.assertIn("\\u202e", output)
                if view == "learn":
                    for target in ("OWN", "REVIEW", "REFERENCE"):
                        self.assertIn(target + " | " + LABELS[locale]["selected"], output)
                if view == "delegate":
                    self.assertIn("DELEGATE | " + LABELS[locale]["selected"], output)
                    self.assertIn("mastery_assessment=NOT_ASSESSED", output)
                    self.assertIn("delegation_grants_authority=False", output)
        output = StringIO()
        with redirect_stdout(output):
            display({"catalog": {"learning": [{"id": "unsafe\x1b[0m\u202e", "concept": "Synthetic ID"}]}}, "en", "dictionary")
        self.assertNotIn("\x1b", output.getvalue())
        self.assertNotIn("\u202e", output.getvalue())

    def test_recorded_method_references_keep_unknown_outcomes_and_requirements(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            snapshot = deepcopy(store.project_snapshot())
        state = snapshot["states"][0]
        ref = state["request_ref"]
        state.setdefault("verifications", {})["fixture-plan"] = {
            "plan": {"spec": {"method": "TEST", "target_path": "fixture.json", "property": "Frozen fixture only",
                               "checks": [{"id": "one", "kind": "json.equals", "pointer": "/value", "expected": 1}],
                               "negative_controls": []}}, "source_ref": ref, "status": "OUTCOME_UNKNOWN"}
        fixture = SimpleNamespace(project_id=self.cfg["project"]["id"], project_snapshot=lambda: snapshot)
        before = deepcopy(snapshot)
        result = project_ownership_dictionary(fixture, None, "en", view="delegate")
        method = result["verification_methods"][0]
        self.assertEqual(method["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(method["ownership_role"], "SYSTEM_REFERENCE")
        self.assertIsNone(method["selected_target"])
        self.assertEqual(method["authority"], "REFERENCE_ONLY")
        self.assertIn("NORMAL_PERMISSION_AND_SCOPE_CHECKS", method["reuse_requires"])
        self.assertEqual(method["source_refs"], [ref])
        self.assertEqual(result["learning"], [])
        self.assertEqual(snapshot, before)
        output = StringIO()
        with redirect_stdout(output):
            display({"catalog": result}, "en", "dictionary")
        self.assertIn("SYSTEM_REFERENCE", output.getvalue())
        self.assertIn("OUTCOME_UNKNOWN", output.getvalue())
        self.assertIn(ref, output.getvalue())

    def test_byte_budget_counts_omitted_choices(self):
        for index in range(8):
            self.raise_item("large-" + str(index), "OWN", concept="z" * 950)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            result = project_ownership_dictionary(store, None, "en", view="learn", max_bytes=4096)
        self.assertLessEqual(len(canonical(result).encode("utf-8")), 4096)
        self.assertEqual(len(result["learning"]) + result["truncated"]["learning"], 8)

    def test_invalid_view_limit_and_run_use_normal_cli_errors(self):
        self.call("--view", "automatic", error="ARGUMENTS")
        self.call("--view", "learn", "--limit", "0", error="ARGUMENTS")
        self.call("--view", "delegate", "--limit", "65", error="ARGUMENTS")
        self.call("--view", "learn", "--run", "missing", error="RUN_NOT_FOUND")


if __name__ == "__main__":
    unittest.main(verbosity=2)
