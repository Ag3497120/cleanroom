"""Voluntary curriculum behavior and authority/source counterexamples."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
import tempfile
import unittest
import uuid

from verantyx import config
from verantyx.adapters.proposal_validation import validate_proposal
from verantyx.application import iso, record_run
from verantyx.domain.codec import digest
from verantyx.domain.events import citation, make_event, validate_event
from verantyx.errors import LedgerError
from verantyx.growth import deltas, template_candidates
from verantyx.kernel.reducer import projection, reduce_event, replay
from verantyx.learning import (
    EVENT_ACTORS, TARGETS, candidate_payload, control_learning, is_learning_command,
    list_learning, project_learning,
)
from verantyx.storage.sqlite import EventStore


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.clock = lambda: datetime(2026, 9, 6, tzinfo=timezone.utc)
        self.start = record_run(self.root, self.cfg, request="判断を使う条件を記録する", run_id="first", clock=self.clock)
        self.anchor = self.start["state"]["request_ref"]

    def tearDown(self):
        self.tmp.cleanup()

    def events(self, run_id="first"):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events(run_id)

    def command(self, operation, run_id="first", **kwargs):
        return control_learning(self.root, self.cfg, run_id, operation, clock=self.clock, **kwargs)

    def raise_candidate(self, **kwargs):
        values = {"concept": "適用条件の確認", "concept_id": "scope_review", "why_now": "同じ判断を別問題に使うため",
                  "minimum_model": "判断と適用範囲を別に記録する", "counterexample": "リスクの異なる対象へ無条件に再利用する",
                  "check": "再利用を拒否するべき条件を説明する", "source_refs": [self.anchor]}
        return self.command("raise", **{**values, **kwargs})

    def append_human_trigger(self):
        previous = self.events()
        command = str(uuid.uuid4())
        event = make_event(self.cfg["project"]["id"], "first", len(previous) + 1, command, iso(self.clock()),
                           "HumanDecisionRecorded", {"point_id": "separate", "choice": "isolate", "reason": "変更を残す",
                           "scope": {"project_id": self.cfg["project"]["id"], "component": "writer", "workload": "parallel",
                                     "risk": "HIGH", "decision_type": "parallel_writers"}}, str(uuid.uuid4()), previous[-1])
        evaluation = make_event(self.cfg["project"]["id"], "first", len(previous) + 2, command, iso(self.clock()),
                                "EvaluationRecorded", {"as_of": iso(self.clock()), "evaluator": "m1.v1"}, str(uuid.uuid4()), event)
        with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
            store.append("trigger", digest("trigger"), "first", len(previous), [event, evaluation])

    def test_full_lifecycle_keeps_targets_submissions_and_history_separate(self):
        raised = self.raise_candidate(key="raise")
        identity = raised["candidate_id"]
        item = raised["candidates"][0]
        self.assertTrue(item["target_is_suggestion"])
        self.assertEqual(item["mastery_evidence"], "NONE")
        for target in TARGETS:
            view = self.command("target", candidate_id=identity, target=target, reason="本人の選択")
            item = view["candidates"][0]
            self.assertEqual(item["ownership_target"], target)
            self.assertFalse(item["target_is_suggestion"])
        deferred = self.command("defer", candidate_id=identity, reason="先に開発を進める")
        self.assertEqual(deferred["state"]["deltas"]["human_delta"], [])
        self.assertEqual(deferred["candidates"][0]["status"], "DEFERRED")
        self.assertEqual(deferred["state"]["assessment"], self.start["state"]["assessment"])
        with self.assertRaises(LedgerError) as error:
            self.command("explain", candidate_id=identity, statement="棚上げ中の提出")
        self.assertEqual(error.exception.code, "LEARNING_STAGE")
        resumed = self.command("resume", candidate_id=identity, reason="必要になったため再開する")
        self.assertEqual(resumed["candidates"][0]["cycle"], 2)
        for operation in ("explain", "counterexample", "apply", "transfer"):
            view = self.command(operation, candidate_id=identity, statement="本人が報告した内容: " + operation,
                                source_refs=[self.anchor], key=operation)
        item = view["candidates"][0]
        self.assertEqual(item["submission_state"], "TRANSFERRED")
        self.assertEqual(item["mastery_evidence"], "SELF_REPORTED")
        self.assertEqual(item["mastery_assessment"], "NOT_ASSESSED")
        self.assertIsNone(item["assessment"])
        self.assertFalse(item["externally_verified"])
        self.assertEqual(len(item["evidence"]), 4)
        self.assertEqual(len(item["history"]), 11)
        refs = {citation(event) for event in self.events()}
        for evidence in item["evidence"]:
            self.assertEqual(evidence["evidence_basis"], "SELF_REPORT")
            self.assertFalse(evidence["externally_verified"])
            self.assertEqual(evidence["cycle"], 2)
            self.assertIn(evidence["source_ref"], refs)
            self.assertTrue(set(evidence["source_refs"]).issubset(refs))
        self.assertEqual(view["state"]["assessment"]["mastery_evidence"], "NONE")

    def test_legacy_template_can_be_collected_or_selected_without_new_identity(self):
        self.append_human_trigger()
        before = list_learning(self.root, self.cfg, "first")
        suggestion = before["candidates"][0]
        self.assertEqual(suggestion["concept"], "branch分離とworktree分離の違い")
        self.assertFalse(suggestion["recorded"])
        identity = suggestion["id"]
        selected = self.command("target", candidate_id=identity, target="OWN", reason="本人が保有する")
        self.assertEqual(selected["candidate_id"], identity)
        self.assertEqual(len(selected["candidates"]), 1)
        self.assertEqual(selected["candidates"][0]["origin"], "TEMPLATE")
        self.assertEqual(selected["candidates"][0]["ownership_target"], "OWN")
        self.assertTrue(selected["candidates"][0]["recorded"])
        collected = self.command("collect", key="collect")
        prior_count = len(self.events())
        duplicate = self.command("collect", key="collect")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["candidate_ids"], collected["candidate_ids"])
        self.assertEqual(len(self.events()), prior_count)
        self.command("collect", key="collect-again")
        self.assertEqual(sum(event["type"] == "LearningCandidateRaised" for event in self.events()), 1)

    def test_local_duplicates_retain_key_receipts_and_reject_conflicting_content(self):
        first = self.raise_candidate(key="save")
        duplicate = self.raise_candidate(key="save")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["candidate_id"], duplicate["candidate_id"])
        self.raise_candidate(key="same-candidate-new-key")
        self.assertEqual(sum(event["type"] == "LearningCandidateRaised" for event in self.events()), 1)
        with self.assertRaises(LedgerError) as error:
            self.raise_candidate(key="save", check="異なる入力")
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
        with self.assertRaises(LedgerError) as error:
            self.raise_candidate(key="changed-content", check="異なる入力")
        self.assertEqual(error.exception.code, "LEARNING_CONFLICT")
        with self.assertRaises(LedgerError) as error:
            self.command("target", candidate_id=first["candidate_id"], target="OWN", reason="変更",
                         expected_revision=self.start["state"]["revision"])
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")

    def test_submission_retry_survives_later_changes_without_duplicating_evidence(self):
        identity = self.raise_candidate()["candidate_id"]
        first = self.command("explain", candidate_id=identity, statement="説明を提出する", key="explain-once")
        self.command("target", candidate_id=identity, target="REFERENCE", reason="後で参照する")
        before = len(self.events())
        duplicate = self.command("explain", candidate_id=identity, statement="説明を提出する", key="explain-once")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["projection_hash"], duplicate["projection_hash"])
        self.assertEqual(len(self.events()), before)
        current = list_learning(self.root, self.cfg, "first")["candidates"][0]
        self.assertEqual(len(current["evidence"]), 1)
        self.assertEqual(current["ownership_target"], "REFERENCE")
        with self.assertRaises(LedgerError) as error:
            self.command("explain", candidate_id=identity, statement="違う説明", key="explain-once")
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_missing_candidates_and_cross_run_candidates_or_sources_are_rejected(self):
        identity = self.raise_candidate()["candidate_id"]
        other = record_run(self.root, self.cfg, request="別タスク", run_id="other", clock=self.clock)
        for run_id, target in (("first", "missing"), ("other", identity)):
            with self.assertRaises(LedgerError) as error:
                self.command("target", run_id=run_id, candidate_id=target, target="OWN", reason="本人の選択")
            self.assertEqual(error.exception.code, "LEARNING_NOT_FOUND")
        for ref in (other["state"]["request_ref"], self.cfg["project"]["id"] + ":" + str(uuid.uuid4())):
            with self.assertRaises(LedgerError) as error:
                self.command("explain", candidate_id=identity, statement="報告", source_refs=[ref])
            self.assertEqual(error.exception.code, "LEARNING_SOURCE")
        with self.assertRaises(LedgerError):
            self.raise_candidate(source_refs=[other["state"]["request_ref"]], concept_id="elsewhere")
        with self.assertRaises(LedgerError) as error:
            self.command("collect", run_id="absent")
        self.assertEqual(error.exception.code, "RUN_NOT_FOUND")

    def test_future_source_and_false_template_are_rejected_during_replay(self):
        raised = self.raise_candidate()
        previous = self.events()
        identity = raised["candidate_id"]
        event_id = str(uuid.uuid4())
        event = make_event(self.cfg["project"]["id"], "first", len(previous) + 1, str(uuid.uuid4()), iso(self.clock()),
                           "SelfExplanationSubmitted", {"candidate_id": identity,
                           "candidate_hash": raised["candidates"][0]["candidate_hash"], "statement": "自己参照を証拠にする",
                           "source_refs": [self.cfg["project"]["id"] + ":" + event_id], "evidence_basis": "SELF_REPORT"},
                           event_id, previous[-1])
        with self.assertRaises(LedgerError) as error:
            replay([*previous, event])
        self.assertEqual(error.exception.code, "LEARNING_SOURCE")
        self.append_human_trigger()
        previous = self.events()
        payload = candidate_payload(template_candidates(replay(previous))[0])
        payload["minimum_model"] = "偽の定型候補"
        event = make_event(self.cfg["project"]["id"], "first", len(previous) + 1, str(uuid.uuid4()), iso(self.clock()),
                           "LearningCandidateRaised", payload, str(uuid.uuid4()), previous[-1])
        with self.assertRaises(LedgerError) as error:
            replay([*previous, event])
        self.assertEqual(error.exception.code, "LEARNING_SOURCE")

    def test_no_event_or_proposal_can_turn_a_submission_into_certified_mastery(self):
        raised = self.raise_candidate()
        self.command("explain", candidate_id=raised["candidate_id"], statement="理解したと自己申告する")
        original = [event for event in self.events() if event["type"] == "SelfExplanationSubmitted"][0]
        for field, value in (("externally_verified", True), ("assessment", "PASSED"), ("evidence_basis", "VERIFIED")):
            forged = deepcopy(original)
            forged["payload"][field] = value
            forged["event_hash"] = digest({key: val for key, val in forged.items() if key != "event_hash"})
            with self.assertRaises(LedgerError):
                validate_event(forged)
        forged = deepcopy(original)
        forged["actor_kind"] = "recorded_proposal"
        forged["event_hash"] = digest({key: val for key, val in forged.items() if key != "event_hash"})
        with self.assertRaises(LedgerError):
            validate_event(forged)
        base = {"schema_version": 1, "task_id": "first", "context_revision": 0, "response_locale": "ja",
                "summary": "提案", "claims": [], "actions": [], "unknowns": []}
        for kind in EVENT_ACTORS:
            with self.assertRaises(LedgerError) as error:
                validate_proposal({**base, kind: original["payload"]})
            self.assertEqual(error.exception.code, "PROPOSAL_INVALID")

    def test_replay_has_no_clock_file_model_network_or_random_dependency(self):
        identity = self.raise_candidate()["candidate_id"]
        self.command("apply", candidate_id=identity, statement="実務適用の報告")
        events = self.events()
        expected = projection(replay(events))
        prior = replay(events[:-1])
        untouched = deepcopy(prior)
        with mock.patch("builtins.open", side_effect=AssertionError("I/O")), \
             mock.patch("pathlib.Path.open", side_effect=AssertionError("I/O")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("uuid.uuid4", side_effect=AssertionError("random")), \
             mock.patch("time.time", side_effect=AssertionError("clock")), \
             mock.patch("verantyx.application.now", side_effect=AssertionError("clock")), \
             mock.patch("socket.socket", side_effect=AssertionError("network")):
            self.assertEqual(projection(replay(events)), expected)
            self.assertEqual(projection(reduce_event(prior, events[-1])), expected)
        self.assertEqual(prior, untouched)

    def test_off_mode_suppresses_delta_without_discarding_saved_history(self):
        self.cfg["learning"]["mode"] = "off"
        off = record_run(self.root, self.cfg, request="学習を停止して進める", run_id="off", clock=self.clock)
        saved = self.raise_candidate(run_id="off", source_refs=[off["state"]["request_ref"]])
        identity = saved["candidate_id"]
        self.command("target", run_id="off", candidate_id=identity, target="DELEGATE", reason="実装を続ける")
        view = list_learning(self.root, self.cfg, "off")
        self.assertEqual(view["human_delta"], [])
        self.assertEqual(len(view["candidates"]), 1)
        self.assertEqual(view["candidates"][0]["ownership_target"], "DELEGATE")
        self.assertEqual(saved["state"]["assessment"], off["state"]["assessment"])

    def test_short_delta_is_bounded_and_complete_curriculum_keeps_every_item(self):
        for index in range(4):
            self.raise_candidate(concept_id="concept" + str(index))
        view = list_learning(self.root, self.cfg, "first")
        self.assertEqual(len(view["human_delta"]), self.cfg["learning"]["max_items"])
        self.assertEqual(len(view["candidates"]), 4)

    def test_archive_keeps_learning_sources_and_stays_reference_only(self):
        identity = self.raise_candidate()["candidate_id"]
        self.command("transfer", candidate_id=identity, statement="別問題への転用の自己申告")
        expected = list_learning(self.root, self.cfg, "first")["candidates"]
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            raw = store.export().encode()
        with tempfile.TemporaryDirectory() as other:
            cfg = config.defaults(Path(other), "ja")
            config.save(Path(other), cfg, None)
            with EventStore(other, cfg["project"]["id"], create=True) as store:
                imported = store.import_archive(raw, iso(self.clock()))
                self.assertEqual(store.events(), [])
            view = list_learning(other, cfg, "first", imported["archive_id"])
            self.assertEqual(view["candidates"], expected)
            self.assertEqual(view["trust"], "ARCHIVE_ONLY")
            with self.assertRaises(LedgerError) as error:
                control_learning(other, cfg, "first", "target", candidate_id=identity, target="OWN", reason="選択")
            self.assertEqual(error.exception.code, "RUN_NOT_FOUND")

    def test_learning_command_whitelist_does_not_exempt_context_changes(self):
        self.command("collect", key="empty-collection")
        events = self.events()
        command = events[-1]["command_id"]
        self.assertTrue(is_learning_command(events, command))
        self.assertFalse(is_learning_command(events, events[0]["command_id"]))
        mixed = deepcopy(events)
        mixed[-2]["type"] = "ProposalRecorded"
        self.assertFalse(is_learning_command(mixed, command))
        self.assertFalse(is_learning_command(events, str(uuid.uuid4())))

    def test_backward_state_and_adopted_delta(self):
        state = deepcopy(self.start["state"])
        state.pop("learning_candidates", None)
        state.pop("learning_source_events", None)
        self.assertEqual(project_learning(state), [])
        self.assertEqual(deltas(state)["human_delta"], [])
        receipt = {"adoption_id": "example", "target_ref": "refs/heads/verantyx/canonical", "base_version": "a" * 40,
                   "commit": "b" * 40, "execution_ref": self.anchor, "recovered": False}
        state["adoptions"] = {"example": {"status": "ADOPTED", "receipt": receipt},
                              "pending": {"status": "PROPOSED", "receipt": {"untrusted": True}}}
        self.assertEqual(deltas(state)["project_delta"]["canonical_changes"], [receipt])


if __name__ == "__main__":
    unittest.main()
