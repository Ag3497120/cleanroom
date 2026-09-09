"""Dictionary regressions using temporary, explicitly artificial project records."""
from copy import deepcopy
from unittest import mock
import unittest
import uuid

import test_learning as learning_fixture
import test_verification as verification_fixture
import test_governance_extended as governance_fixture

from verantyx import assets
from verantyx.application import record_run
from verantyx.domain.codec import canonical, digest
from verantyx.domain.events import make_event
from verantyx.errors import LedgerError
from verantyx.learning import control_learning
from verantyx.storage.sqlite import EventStore


class ReuseDictionaryTests(unittest.TestCase):
    def fixture(self, kind):
        fixture = kind(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        return fixture

    def test_explicit_query_finds_saved_candidate_beyond_short_learning_digest(self):
        f = self.fixture(learning_fixture.LearningTests)
        f.raise_candidate(concept_id="first_concept")
        late = f.raise_candidate(concept_id="later_concept", concept="Later dictionary entry",
                                 why_now="unique-recovery-reason")
        identity = late["candidate_id"]
        f.command("target", candidate_id=identity, target="OWN", reason="artificial ownership choice")
        f.command("explain", candidate_id=identity, statement="private-learning-submission")
        state = record_run(f.root, f.cfg, request="another task", run_id="next", clock=f.clock)["state"]
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            by_concept = assets.project_catalog(store, state, "ja", query="later_concept")
            by_reason = assets.project_catalog(store, state, "ja", query="unique-recovery-reason")
        self.assertEqual([row["id"] for row in by_concept["learning"]], [identity])
        self.assertEqual(by_concept["learning"], by_reason["learning"])
        item = by_reason["learning"][0]
        self.assertEqual(item["owner_run"], "first")
        self.assertEqual(item["project_anchor"], f.anchor)
        self.assertEqual(item["ownership_target"], "OWN")
        self.assertFalse(item["target_is_suggestion"])
        self.assertEqual(item["mastery_assessment"], "NOT_ASSESSED")
        self.assertNotIn("private-learning-submission", canonical(by_reason))
        self.assertEqual(item["authority"], "REFERENCE_ONLY")

    def test_explicit_lookup_can_recover_deferred_saved_learning_without_resuming_it(self):
        f = self.fixture(learning_fixture.LearningTests)
        raised = f.raise_candidate(concept_id="deferred_recovery")
        identity = raised["candidate_id"]
        deferred = f.command("defer", candidate_id=identity, reason="artificial deferral")
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            revision = store.project_revision()
            automatic = assets.project_catalog(store, deferred["state"], "ja")
            explicit = assets.project_catalog(store, None, "ja", query="deferred_recovery")
            self.assertEqual(store.project_revision(), revision)
        self.assertFalse(any(row["id"] == identity for row in automatic["learning"]))
        self.assertEqual([row["id"] for row in explicit["learning"]], [identity])
        self.assertEqual(explicit["learning"][0]["status"], "DEFERRED")

    def test_saved_off_mode_items_are_searchable_without_emitting_suggestions(self):
        f = self.fixture(learning_fixture.LearningTests)
        off = deepcopy(f.cfg)
        off["learning"]["mode"] = "off"
        task = record_run(f.root, off, request="off mode task", run_id="off", clock=f.clock)
        result = control_learning(f.root, off, "off", "raise", concept="Saved off-mode reference",
                                  concept_id="off_reference", why_now="explicitly saved",
                                  minimum_model="recorded principle", counterexample="recorded counterexample",
                                  check="recorded question", source_refs=[task["state"]["request_ref"]], clock=f.clock)
        with EventStore(f.root, off["project"]["id"]) as store:
            automatic = assets.project_catalog(store, result["state"], "ja")
            explicit = assets.project_catalog(store, None, "ja", query="off_reference")
        self.assertFalse(any(row["owner_run"] == "off" for row in automatic["learning"]))
        self.assertEqual([row["id"] for row in explicit["learning"]], [result["candidate_id"]])
        self.assertEqual(result["state"]["deltas"]["human_delta"], [])

    def test_same_concept_in_two_tasks_keeps_distinct_sources_and_ownership(self):
        f = self.fixture(learning_fixture.LearningTests)
        first = f.raise_candidate(concept_id="shared_concept")
        f.command("target", candidate_id=first["candidate_id"], target="OWN", reason="artificial choice one")
        task = record_run(f.root, f.cfg, request="second occurrence", run_id="second", clock=f.clock)
        second = control_learning(f.root, f.cfg, "second", "raise", concept="Another wording",
                                  concept_id="shared_concept", why_now="another occurrence",
                                  minimum_model="different principle", counterexample="another counterexample",
                                  check="another question", source_refs=[task["state"]["request_ref"]], clock=f.clock)
        control_learning(f.root, f.cfg, "second", "target", candidate_id=second["candidate_id"], target="DELEGATE",
                         reason="artificial choice two", clock=f.clock)
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            result = assets.project_catalog(store, None, "ja", query="shared_concept")
        self.assertEqual(len(result["learning"]), 2)
        by_run = {row["owner_run"]: row for row in result["learning"]}
        self.assertEqual(by_run["first"]["ownership_target"], "OWN")
        self.assertEqual(by_run["second"]["ownership_target"], "DELEGATE")
        self.assertNotEqual(by_run["first"]["source_refs"], by_run["second"]["source_refs"])
        from verantyx.sovereignty import report
        inventory = report(f.root, f.cfg)
        self.assertEqual(len(inventory["concepts"][0]["occurrences"]), 2)
        self.assertEqual(inventory["metrics"]["learning_candidates"], 2)
        self.assertFalse(inventory["authority_granted"])

    def test_applicable_other_task_rule_precedes_own_rule_with_an_exception(self):
        f = self.fixture(governance_fixture.ExtendedFixture)
        own, _ = f.promote("first")
        other = f.draft("other")
        f.command("rule-shadow", other)
        f.command("rule-confirm", other)
        f.command("rule-activate", other)
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            original = store.project_snapshot()["rules"][own]["scope"]
        from verantyx.domain.rule_extensions import exact_policy
        policy = exact_policy(original, 1)
        policy["exceptions"] = [{"id": "needs-other-contract", "scope": original, "reason": "artificial exception"}]
        f.accepted_policy(own, policy)
        current = record_run(f.root, f.cfg, run_id="first", resume=True, clock=f.clock, backend=f.backend)
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            result = assets.project_catalog(store, current["state"], "ja", limit=1)
        self.assertEqual([row["id"] for row in result["rules"]], [other])
        self.assertTrue(result["rules"][0]["applicable_to_requested_context"])
        self.assertEqual(result["truncated"]["rules"], 1)

    def test_target_match_survives_more_than_twenty_four_other_methods(self):
        f = self.fixture(verification_fixture.VerificationTests)
        paths = [f"target-{number}.json" for number in range(25)]
        for path in paths:
            (f.root / path).write_text('{"answer":42}')
        record_run(f.root, f.cfg, run_id="verify", resume=True, observe_paths=paths, clock=f.clock)
        for number, path in enumerate(paths):
            spec = deepcopy(f.spec)
            spec["target_path"] = path
            last = f.plan(spec, key="different-target-" + str(number))
        methods = assets.project_assets(last["state"])["verification_methods"]
        # The last ID was certainly excluded by the former lexical top-24 policy.
        selected = max(methods, key=lambda row: row["id"])
        current = record_run(f.root, f.cfg, request="inspect selected target", run_id="next",
                             observe_paths=[selected["target"]], clock=f.clock)["state"]
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            result = assets.project_catalog(store, current, "ja")
        self.assertEqual(result["verification_methods"][0]["id"], selected["id"])
        self.assertEqual(result["truncated"]["verification_methods"], 1)
        self.assertEqual(result["verification_methods"][0]["reuse_requires"], selected["reuse_requires"])
        self.assertEqual(result["verification_methods"][0]["authority"], "REFERENCE_ONLY")

    def test_many_unrelated_streams_do_not_disable_explicit_dictionary_search(self):
        f = self.fixture(learning_fixture.LearningTests)
        saved = f.raise_candidate(concept_id="retained_after_twenty_thousand")
        with EventStore(f.root, f.cfg["project"]["id"], create=True) as store:
            prototype = store.events("first")[0]
            rows = []
            # Each small stream is valid; their sum formerly hit a project-wide cap.
            for number in range(10000):
                stream, command = "unrelated-" + str(number), str(uuid.uuid4())
                first = make_event(store.project_id, stream, 1, command, prototype["recorded_at"],
                                   "TaskRequested", deepcopy(prototype["payload"]), str(uuid.uuid4()), None)
                last = make_event(store.project_id, stream, 2, command, prototype["recorded_at"],
                                  "EvaluationRecorded", {"as_of": prototype["recorded_at"], "evaluator": "m1.v1"},
                                  str(uuid.uuid4()), first)
                rows.extend((event["event_id"], stream, event["revision"], canonical(event)) for event in (first, last))
            # Bulk fixture insertion only; normal readers still validate every event.
            with store._transaction(write=True):
                store.connection.executemany("INSERT INTO events(event_id,stream_id,revision,event_json) VALUES(?,?,?,?)", rows)
            result = assets.project_catalog(store, None, "ja", query="retained_after_twenty_thousand")
        self.assertGreater(result["project_revision"], 20000)
        self.assertEqual([row["id"] for row in result["learning"]], [saved["candidate_id"]])


class SnapshotIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = learning_fixture.LearningTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        f = self.fixture
        self.store = EventStore(f.root, f.cfg["project"]["id"], create=True)
        self.addCleanup(self.store.close)

    def test_repeated_snapshot_reuses_validation_and_returned_values_cannot_mutate_cache(self):
        import verantyx.storage.sqlite as storage
        with mock.patch.object(storage, "replay", wraps=storage.replay) as check:
            first = self.store.project_snapshot()
            self.assertEqual(check.call_count, 1)
            first["events"][0]["payload"]["request"] = "corrupted caller copy"
            first["states"][0]["request"] = "corrupted caller state"
            again = self.store.project_snapshot()
            self.assertEqual(check.call_count, 1)
        self.assertEqual(again["states"][0]["request"], self.fixture.start["state"]["request"])
        self.assertEqual(again["events"][0]["payload"]["request"], self.fixture.start["state"]["request"])

    def test_external_and_same_connection_appends_invalidate_snapshot(self):
        f = self.fixture
        before = self.store.project_snapshot()
        f.raise_candidate(concept_id="new_external_candidate")
        after = self.store.project_snapshot()
        self.assertGreater(after["project_revision"], before["project_revision"])
        self.assertEqual(len(after["states"][0]["learning_candidates"]), 1)
        events = after["events"]
        command = str(uuid.uuid4())
        evaluation = make_event(self.store.project_id, "first", events[-1]["revision"] + 1, command,
                                events[-1]["recorded_at"], "EvaluationRecorded", events[-1]["payload"],
                                str(uuid.uuid4()), events[-1])
        self.store.append("own-append", digest("own-append"), "first", events[-1]["revision"], [evaluation])
        own = self.store.project_snapshot()
        self.assertEqual(own["project_revision"], after["project_revision"] + 1)

    def test_tampering_without_revision_change_invalidates_cache_and_is_rejected(self):
        self.store.project_snapshot()
        self.store.connection.execute("DROP TRIGGER events_no_update")
        self.store.connection.execute("UPDATE events SET event_json='{}' WHERE revision=1")
        with self.assertRaises(LedgerError):
            self.store.project_snapshot()

    def test_external_tampering_without_revision_change_is_rejected(self):
        self.store.project_snapshot()
        f = self.fixture
        with EventStore(f.root, f.cfg["project"]["id"], create=True) as writer:
            writer.connection.execute("DROP TRIGGER events_no_update")
            writer.connection.execute("UPDATE events SET event_json='{}' WHERE revision=1")
        with self.assertRaises(LedgerError):
            self.store.project_snapshot()

    def test_valid_envelopes_with_broken_chain_still_fail_snapshot_replay(self):
        before = self.store.project_snapshot()
        event = deepcopy(before["events"][-1])
        event["prev_hash"] = "0" * 64
        event["event_hash"] = digest({key: value for key, value in event.items() if key != "event_hash"})
        self.store.connection.execute("DROP TRIGGER events_no_update")
        self.store.connection.execute("UPDATE events SET event_json=? WHERE event_id=?", (canonical(event), event["event_id"]))
        with self.assertRaises(LedgerError):
            self.store.project_snapshot()

    def test_rolled_back_transaction_cannot_leave_a_cached_uncommitted_projection(self):
        before = self.store.project_snapshot()
        events = deepcopy(before["events"])
        events[0]["payload"]["request"] = "uncommitted replacement"
        for index, event in enumerate(events):
            if index:
                event["prev_hash"] = events[index - 1]["event_hash"]
            event["event_hash"] = digest({key: value for key, value in event.items() if key != "event_hash"})
        self.store.connection.execute("DROP TRIGGER events_no_update")
        with self.assertRaisesRegex(RuntimeError, "rollback fixture"):
            with self.store._transaction(write=True):
                self.store.connection.executemany("UPDATE events SET event_json=? WHERE event_id=?",
                                                  [(canonical(event), event["event_id"]) for event in events])
                inside = self.store.project_snapshot()
                self.assertEqual(inside["states"][0]["request"], "uncommitted replacement")
                raise RuntimeError("rollback fixture")
        after = self.store.project_snapshot()
        self.assertEqual(after["states"][0]["request"], before["states"][0]["request"])
