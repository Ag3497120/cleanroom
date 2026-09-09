"""External learning content stays scoped, attributable, voluntary, and non-authoritative."""
from copy import deepcopy
import json
import os
import subprocess
import sys
from unittest import mock

from test_constitution import Fixture
from test_model_connections import HTTPFixture
from verantyx.application import get_projection
from verantyx.domain.codec import canonical, digest
from verantyx.domain.events import citation, make_event
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.learning import control_learning, is_learning_command, project_learning
from verantyx.learning_external import generate
from verantyx.storage.sqlite import EventStore, parse_archive


class LearningConnectionTests(Fixture):
    def setUp(self):
        super().setUp()
        run = self.run_task("task")
        result = control_learning(self.root, self.cfg, "task", "raise", key="raise", clock=self.clock,
                                  candidate_id="permission", concept_id="permission", concept="Proposal and permission",
                                  why_now=["Fixture concept"], minimum_model="Separate proposal and authority.",
                                  counterexample="A proposal cannot approve itself.", check="Explain the distinction.",
                                  source_refs=[run["state"]["request_ref"]])
        self.candidate = result["candidate_ids"][0]
        self.http = HTTPFixture()
        self.adapter = self.root / "learning-model.json"
        self.adapter.write_text(canonical(self.http.configuration("ollama")))

    def tearDown(self):
        self.http.close()
        super().tearDown()

    def state(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return get_projection(store, "task")["state"]

    def generate(self, operation="material", key="external", **kwargs):
        return generate(self.root, self.cfg, "task", candidate_id=self.candidate, operation=operation,
                        adapter_path=self.adapter, key=key, expected_revision=self.state()["revision"], clock=self.clock, **kwargs)

    def answer(self):
        result = control_learning(self.root, self.cfg, "task", "explain", candidate_id=self.candidate,
                                  statement="Fixture answer: permissions and proposals have different roles.", key="answer", clock=self.clock)
        return result["state"]["learning_candidates"][self.candidate]["evidence"][-1]["source_ref"]

    def test_material_connects_real_provider_and_remains_a_proposal(self):
        result = self.generate()
        item = result["state"]["learning_candidates"][self.candidate]
        self.assertEqual(len(item["external_materials"]), 1)
        self.assertEqual(result["provenance"]["provider"], "ollama")
        view = next(c for c in project_learning(result["state"]) if c["id"] == self.candidate)
        self.assertEqual(view["mastery_assessment"], "NOT_ASSESSED")
        self.assertFalse(view["externally_verified"])
        self.assertTrue(view["target_is_suggestion"])
        self.assertNotIn("submission", json.loads(self.http.calls[0]["body"]["prompt"])["candidate"])
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("task")
            self.assertTrue(is_learning_command(events, events[-1]["command_id"]))
            self.assertEqual(replay(events)["learning_candidates"], result["state"]["learning_candidates"])
            self.assertEqual(len(parse_archive(store.export().encode())["events"]), len(events))

    def test_free_text_assessment_binds_one_submission_and_supplied_rubric(self):
        selected = self.answer()
        result = self.generate("assess", submission_ref=selected, rubric="Check whether the answer distinguishes a proposal from an execution permit.")
        assessment = result["external_result"]
        self.assertEqual(assessment["submission_ref"], selected)
        self.assertEqual(assessment["scope"], "SELECTED_SUBMISSION_AND_RUBRIC_ONLY")
        self.assertEqual(result["state"]["learning_candidates"][self.candidate]["external_assessments"][0]["oracle_independence"], "NOT_ESTABLISHED")
        view = next(c for c in project_learning(result["state"]) if c["id"] == self.candidate)
        self.assertEqual(view["mastery_evidence"], "SELF_REPORTED")
        self.assertEqual(view["mastery_assessment"], "NOT_ASSESSED")
        sent = json.loads(self.http.calls[0]["body"]["prompt"])
        self.assertEqual(sent["submission"]["source_ref"], selected)
        self.assertEqual(sent["source_refs"], [view["source_ref"], selected])
        self.assertNotIn("events", sent)
        self.assertNotIn("selected_files", sent)

    def test_wrong_or_prior_cycle_submission_is_not_sent(self):
        selected = self.answer()
        control_learning(self.root, self.cfg, "task", "defer", candidate_id=self.candidate, reason="fixture", clock=self.clock)
        control_learning(self.root, self.cfg, "task", "resume", candidate_id=self.candidate, reason="fixture", clock=self.clock)
        for source in (selected, "nonexistent"):
            with self.subTest(source=source), self.assertRaises(LedgerError):
                self.generate("assess", key="bad-" + source.replace(":", "-"), submission_ref=source, rubric="fixture")
        self.assertEqual(self.http.calls, [])

    def test_started_call_without_saved_response_is_never_repeated(self):
        revision = self.state()["revision"]
        def fail(stage):
            if stage == "after_started":
                raise RuntimeError("interrupted")
        with self.assertRaises(RuntimeError):
            self.generate(fault=fail)
        with self.assertRaises(LedgerError) as error:
            generate(self.root, self.cfg, "task", candidate_id=self.candidate, operation="material", adapter_path=self.adapter,
                     key="external", expected_revision=revision, clock=self.clock)
        self.assertEqual(error.exception.code, "BRIDGE_OUTCOME_UNKNOWN")
        self.assertEqual(self.http.calls, [])

    def test_saved_response_and_committed_event_recover_without_new_model_call(self):
        for stage in ("after_response", "after_record"):
            with self.subTest(stage=stage):
                revision = self.state()["revision"]
                def fail(current):
                    if current == stage:
                        raise RuntimeError("interrupted")
                with self.assertRaises(RuntimeError):
                    self.generate(key=stage, fault=fail)
                calls = len(self.http.calls)
                result = generate(self.root, self.cfg, "task", candidate_id=self.candidate, operation="material", adapter_path=self.adapter,
                                  key=stage, expected_revision=revision, clock=self.clock)
                self.assertTrue(result["ok"])
                self.assertEqual(len(self.http.calls), calls)

    def test_context_changes_after_model_response_reject_recording(self):
        def change(stage):
            if stage == "after_response":
                control_learning(self.root, self.cfg, "task", "defer", candidate_id=self.candidate, reason="fixture", clock=self.clock)
        with self.assertRaises(LedgerError) as error:
            self.generate(fault=change)
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")
        self.assertNotIn("external_materials", self.state()["learning_candidates"][self.candidate])
        self.assertEqual(len(self.http.calls), 1)

    def test_response_cannot_claim_human_authority_or_widen_scope(self):
        self.http.mode = "self_approve"
        with self.assertRaises(LedgerError):
            self.generate()
        self.assertNotIn("external_materials", self.state()["learning_candidates"][self.candidate])

    def test_replay_rejects_tampered_scope_submission_and_mastery(self):
        self.answer()
        result = self.generate()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("task")
        original = events[-2]
        modifications = ({"mastery_assessment": "MASTERED"}, {"cycle": True}, {"request_sha256": "0" * 64},
                         {"response": {**original["payload"]["response"], "scope": "ALL_CONCEPTS"}})
        for update in modifications:
            with self.subTest(update=list(update)), self.assertRaises(LedgerError):
                payload = deepcopy(original["payload"])
                payload.update(update)
                payload["response_sha256"] = digest(payload["response"])
                altered = make_event(original["project_id"], "task", original["revision"], original["command_id"],
                                     original["recorded_at"], original["type"], payload, original["event_id"], events[-3])
                replay([*events[:-2], altered])

    def test_explicit_learning_command_runs_when_learning_display_is_off(self):
        self.cfg["learning"]["mode"] = "off"
        self.assertTrue(self.generate()["ok"])

    def test_cli_material_and_event_labels_exist_in_all_languages(self):
        result = self.generate()
        for locale in ("en", "ja", "zh-Hans", "ko", "es"):
            process = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(self.root), "--lang", locale, "events", "task"],
                                     env={**os.environ, "PYTHONPATH": str(__import__('pathlib').Path(__file__).resolve().parents[1] / "src")},
                                     capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
