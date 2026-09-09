"""Negative cases for bounded exercises, provenance and voluntary repetition."""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

from verantyx import config
from verantyx.application import iso, record_run
from verantyx.commands_learning import COMMANDS, LABELS, dispatch, display, register, translation_entries, utc_timestamp
from verantyx.domain.codec import digest
from verantyx.domain.events import citation, make_event, validate_event
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import projection, replay
from verantyx.learning import control_learning, is_learning_command, list_learning
from verantyx.learning_exercises import (
    EVENT_ACTORS, control_exercises, due_reviews, grade, inspect_exercises, public_exercise, validate_exercise,
)
from verantyx.learning_materials import LANGUAGES, MATERIALS, builtin_exercise
from verantyx.storage.sqlite import EventStore


class LearningExerciseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.time = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)
        self.clock = lambda: self.time
        self.start = record_run(self.root, self.cfg, request="隔離した作業場所を選ぶ", run_id="first", clock=self.clock)
        self.anchor = self.start["state"]["request_ref"]
        self.identity = self.candidate("practice")
        self.spec = builtin_exercise("parallel_writers", "ja")
        self.answers = {q["id"]: deepcopy(q["rubric"]["expected"]) for q in self.spec["questions"]}

    def tearDown(self):
        self.tmp.cleanup()

    def candidate(self, identity, *, run_id="first", anchor=None):
        return control_learning(self.root, self.cfg, run_id, "raise", candidate_id=identity,
            concept="作業場所の分離", concept_id="parallel_writers", why_now="並列変更を守るため",
            minimum_model="作業ファイルとindexを分ける", counterexample="別branchだが同じ作業ファイル",
            check="安全な二人の作業場所を選ぶ", source_refs=[anchor or self.anchor], clock=self.clock)["candidate_id"]

    def command(self, operation, **kwargs):
        return control_exercises(self.root, self.cfg, "first", operation, candidate_id=self.identity,
            exercise_id=self.spec["id"] if operation != "register" else None, clock=self.clock, **kwargs)

    def events(self):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events("first")

    def register(self, **kwargs):
        return self.command("register", document=self.spec, **kwargs)

    def answer(self, **kwargs):
        return self.command("answer", answers=deepcopy(self.answers), **kwargs)

    def item(self):
        return list_learning(self.root, self.cfg, "first")["candidates"][0]

    def append_event(self, kind, payload, recorded_at=None):
        previous = self.events()
        return make_event(self.cfg["project"]["id"], "first", len(previous) + 1, str(uuid.uuid4()),
            recorded_at or iso(self.clock()), kind, payload, str(uuid.uuid4()), previous[-1])

    def test_all_three_concepts_have_valid_five_language_material_and_real_scoring(self):
        all_titles = []
        for concept in MATERIALS:
            for language in LANGUAGES:
                spec = builtin_exercise(concept, language)
                origin = {"kind": "UNKNOWN", "identity": "Synthetic test input", "model": None, "provider": None}
                answers = {q["id"]: deepcopy(q["rubric"]["expected"]) for q in spec["questions"]}
                self.assertEqual(grade(spec, answers, origin)["status"], "PASSED")
                answers["boundary"] = ["first", "second", "unrelated"]
                failed = grade(spec, answers, origin)
                self.assertEqual((failed["score"], failed["status"]), (2, "FAILED"))
                self.assertEqual(failed["closure"], "BOUNDED")
                self.assertEqual(failed["mastery_claim"], "NOT_ASSESSED")
                all_titles.append(spec["lesson"]["title"])
        self.assertEqual(len(all_titles), len(set(all_titles)))

    def test_answers_are_preregistered_and_assessed_without_changing_ownership_or_mastery(self):
        with self.assertRaises(LedgerError) as error:
            self.answer()
        self.assertEqual(error.exception.code, "LEARNING_EXERCISE_NOT_FOUND")
        self.register()
        before = self.item()
        result = self.answer(key="answer-once")
        item = result["candidates"][0]
        self.assertTrue(item["target_is_suggestion"])
        for key in ("ownership_target", "mastery_evidence", "mastery_assessment", "assessment", "externally_verified", "system_capture"):
            self.assertEqual(item[key], before[key])
        exercise = item["exercises"][0]
        assessment = exercise["assessments"][0]
        self.assertEqual(assessment["result"]["score"], 3)
        self.assertEqual(assessment["attempt_ref"], exercise["attempts"][0]["source_ref"])
        self.assertFalse(assessment["result"]["person_authenticated"])
        self.assertEqual(result["state"]["assessment"], self.start["state"]["assessment"])
        types = [event["type"] for event in self.events()]
        self.assertLess(types.index("LearningExerciseRegistered"), types.index("LearningExerciseAttempted"))
        self.assertLess(types.index("LearningExerciseAttempted"), types.index("LearningExerciseAssessed"))

    def test_custom_structured_transfer_exercise_is_evaluated_by_its_frozen_rubric(self):
        self.spec["id"] = "custom-transfer"
        self.spec["questions"] = [self.spec["questions"][2]]
        self.spec["questions"][0]["competency"] = "TRANSFER"
        self.spec["passing_score"] = 1
        self.register()
        result = self.command("answer", answers={"application": {"scope": "bounded", "authority": "automatic"}})
        assessment = result["candidates"][0]["exercises"][0]["assessments"][0]["result"]
        self.assertEqual(assessment["status"], "FAILED")
        self.assertEqual(assessment["question_results"][0]["competency"], "TRANSFER")
        self.assertEqual(result["candidates"][0]["submission_state"], "EXPOSED")

    def test_closed_schema_rejects_code_self_approval_invalid_rubrics_and_answers(self):
        mutations = [lambda s: s.update(approved=True), lambda s: s.update(passing_score=True),
            lambda s: s["questions"][0]["rubric"].update(execute="__import__('os')"),
            lambda s: s["questions"][0]["rubric"].update(expected="missing"),
            lambda s: s["questions"][0]["choices"].append(deepcopy(s["questions"][0]["choices"][0])),
            lambda s: s["provenance"].update(independence="PROVED")]
        for mutation in mutations:
            spec = deepcopy(self.spec)
            mutation(spec)
            with self.assertRaises(LedgerError):
                validate_exercise(spec)
        self.register()
        bad_answers = [{**self.answers, "passed": True}, {**self.answers, "boundary": ["first", "first"]},
                       {**self.answers, "principle": True}, {**self.answers, "application": {"scope": "bounded"}}]
        for answers in bad_answers:
            with self.assertRaises(LedgerError):
                self.command("answer", answers=answers)
        with self.assertRaises(LedgerError):
            self.answer(answer_origin={})
        self.assertEqual(len(self.item()["exercises"][0]["assessments"]), 0)

    def test_registered_identity_and_concept_cannot_be_rebound(self):
        self.register()
        changed = deepcopy(self.spec)
        changed["questions"][0]["rubric"]["expected"] = "overclaim"
        with self.assertRaises(LedgerError) as error:
            self.command("register", document=changed)
        self.assertEqual(error.exception.code, "LEARNING_EXERCISE_CONFLICT")
        changed["id"] = "new-exercise"
        changed["concept_id"] = "unrelated"
        with self.assertRaises(LedgerError) as error:
            self.command("register", document=changed)
        self.assertEqual(error.exception.code, "LEARNING_EXERCISE_CONFLICT")
        self.register(key="same-exercise-new-operation")
        self.assertEqual(len(self.item()["exercises"]), 1)

    def test_mutating_call_arguments_does_not_change_frozen_event_data(self):
        spec = deepcopy(self.spec)
        self.command("register", document=spec)
        expected = deepcopy(self.item()["exercises"][0]["material"])
        spec["lesson"]["principle"] = "changed"
        self.assertEqual(self.item()["exercises"][0]["material"], expected)

    def test_shared_model_and_provider_are_visible_but_different_names_do_not_prove_independence(self):
        self.spec["provenance"]["author"] = {"kind": "EXTERNAL_MODEL", "identity": "same-agent", "model": "model-1", "provider": "provider-1"}
        self.register()
        same = self.answer(answer_origin=deepcopy(self.spec["provenance"]["author"]))
        independence = same["candidates"][0]["exercises"][0]["assessments"][-1]["result"]["independence"]
        self.assertEqual(independence["declared_overlap"], ["IDENTITY", "MODEL", "PROVIDER"])
        self.assertEqual(independence["status"], "NOT_ESTABLISHED")
        other = self.answer(answer_origin={"kind": "EXTERNAL_MODEL", "identity": "other", "model": "different", "provider": "elsewhere"})
        independence = other["candidates"][0]["exercises"][0]["assessments"][-1]["result"]["independence"]
        self.assertEqual(independence["declared_overlap"], [])
        self.assertEqual(independence["status"], "NOT_ESTABLISHED")

    def test_replay_recomputes_scores_and_rejects_forged_mastery_and_closure(self):
        self.register()
        self.answer()
        events = self.events()
        index = next(i for i, event in enumerate(events) if event["type"] == "LearningExerciseAssessed")
        original = events[index]
        for field, value in (("score", 100), ("status", "FAILED"), ("closure", "PROVED"),
                             ("mastery_claim", "MASTERED"), ("person_authenticated", True)):
            forged = deepcopy(original)
            forged["payload"]["result"][field] = value
            forged["event_hash"] = digest({key: value for key, value in forged.items() if key != "event_hash"})
            with self.assertRaises(LedgerError) as error:
                replay([*events[:index], forged])
            self.assertEqual(error.exception.code, "LEARNING_ASSESSMENT_INVALID")
        forged = deepcopy(original)
        forged["actor_kind"] = "recorded_proposal"
        forged["event_hash"] = digest({key: value for key, value in forged.items() if key != "event_hash"})
        with self.assertRaises(LedgerError):
            validate_event(forged)

    def test_replay_rejects_wrong_exercise_source_and_duplicate_assessment(self):
        self.register()
        self.answer()
        assessed = next(event for event in self.events() if event["type"] == "LearningExerciseAssessed")
        for field, value in (("exercise_hash", "a" * 64), ("attempt_ref", self.anchor)):
            payload = {**deepcopy(assessed["payload"]), field: value}
            with self.assertRaises(LedgerError):
                replay([*self.events(), self.append_event("LearningExerciseAssessed", payload)])
        with self.assertRaises(LedgerError) as error:
            replay([*self.events(), self.append_event("LearningExerciseAssessed", assessed["payload"])])
        self.assertEqual(error.exception.code, "LEARNING_EXERCISE_CONFLICT")

    def test_schedule_due_and_repeat_intervals_are_based_on_recorded_utc(self):
        self.register()
        due = self.time + timedelta(hours=1)
        self.command("schedule", due_at=iso(due), intervals_days=[1, 3, 7], reason="次の作業で確認する")
        state = replay(self.events())
        self.assertEqual(due_reviews(state, iso(self.time))["total_due"], 0)
        self.assertEqual(due_reviews(state, iso(due))["total_due"], 1)
        self.time = due
        self.answer()
        review = self.item()["exercises"][0]["review"]
        self.assertEqual(review["due_at"], iso(self.time + timedelta(days=1)))
        self.assertEqual((review["step"], review["completed_reviews"]), (1, 1))
        self.time += timedelta(days=1)
        self.answer()
        self.assertEqual(self.item()["exercises"][0]["review"]["due_at"], iso(self.time + timedelta(days=3)))
        self.time += timedelta(days=3)
        bad = {**self.answers, "principle": "overclaim"}
        self.command("answer", answers=bad)
        review = self.item()["exercises"][0]["review"]
        self.assertEqual((review["step"], review["completed_reviews"]), (0, 3))
        self.assertEqual(review["due_at"], iso(self.time + timedelta(days=1)))

    def test_defer_delegate_cancel_and_off_suppress_due_without_erasing_history(self):
        self.register()
        self.command("schedule", due_at=iso(self.time), reason="確認する")
        control_learning(self.root, self.cfg, "first", "defer", candidate_id=self.identity, reason="先に進める", clock=self.clock)
        self.assertEqual(inspect_exercises(self.root, self.cfg, "first", clock=self.clock)["total_due"], 0)
        with self.assertRaises(LedgerError) as error:
            self.answer()
        self.assertEqual(error.exception.code, "LEARNING_STAGE")
        control_learning(self.root, self.cfg, "first", "resume", candidate_id=self.identity, reason="再開する", clock=self.clock)
        self.assertEqual(inspect_exercises(self.root, self.cfg, "first", clock=self.clock)["total_due"], 1)
        control_learning(self.root, self.cfg, "first", "target", candidate_id=self.identity, target="DELEGATE", reason="委ねる", clock=self.clock)
        self.assertEqual(inspect_exercises(self.root, self.cfg, "first", clock=self.clock)["total_due"], 0)
        control_learning(self.root, self.cfg, "first", "target", candidate_id=self.identity, target="REFERENCE", reason="参照する", clock=self.clock)
        self.command("cancel", reason="必要時に自分で復習する")
        self.assertEqual(inspect_exercises(self.root, self.cfg, "first", clock=self.clock)["total_due"], 0)
        self.assertEqual(self.item()["exercises"][0]["review"]["status"], "CANCELLED")
        self.cfg["learning"]["mode"] = "off"
        start = record_run(self.root, self.cfg, request="学習なしで進める", run_id="off", clock=self.clock)
        identity = self.candidate("off-practice", run_id="off", anchor=start["state"]["request_ref"])
        for operation, kwargs in (("register", {"document": self.spec}), ("schedule", {"due_at": iso(self.time), "reason": "将来の候補"})):
            control_exercises(self.root, self.cfg, "off", operation, candidate_id=identity, exercise_id=self.spec["id"], clock=self.clock, **kwargs)
        view = inspect_exercises(self.root, self.cfg, "off", clock=self.clock)
        self.assertEqual(view["suppressed"], "LEARNING_OFF")
        self.assertEqual(view["items"], [])
        self.assertEqual(len(list_learning(self.root, self.cfg, "off")["candidates"][0]["exercises"]), 1)

    def test_due_list_honors_max_items_and_retains_full_count(self):
        for index in range(4):
            identity = self.identity if index == 0 else self.candidate("practice" + str(index))
            control_exercises(self.root, self.cfg, "first", "register", candidate_id=identity, document=self.spec, clock=self.clock)
            control_exercises(self.root, self.cfg, "first", "schedule", candidate_id=identity, exercise_id=self.spec["id"],
                due_at=iso(self.time), reason="復習", clock=self.clock)
        result = inspect_exercises(self.root, self.cfg, "first", clock=self.clock)
        self.assertEqual(result["total_due"], 4)
        self.assertEqual(len(result["items"]), self.cfg["learning"]["max_items"])

    def test_schedule_rejects_naive_past_invalid_intervals_and_stale_cancel_source(self):
        self.register()
        for due, intervals in ((iso(self.time - timedelta(seconds=1)), [1]), ("2026-09-06T12:00:00", [1]),
                               (iso(self.time), [True]), (iso(self.time), [3, 1]), (iso(self.time), [1, 1]), (iso(self.time), [0])):
            with self.assertRaises(LedgerError):
                self.command("schedule", due_at=due, intervals_days=intervals, reason="予定")
        self.command("schedule", due_at=iso(self.time), reason="予定")
        item = self.item()
        exercise = item["exercises"][0]
        payload = {"candidate_id": self.identity, "candidate_hash": item["candidate_hash"], "exercise_id": self.spec["id"],
                   "exercise_hash": exercise["exercise_hash"], "schedule_ref": self.anchor, "reason": "偽の取消"}
        with self.assertRaises(LedgerError) as error:
            replay([*self.events(), self.append_event("LearningReviewCancelled", payload)])
        self.assertEqual(error.exception.code, "LEARNING_SOURCE")
        self.assertEqual(utc_timestamp("2026-09-06T12:00:00+00:00"), iso(self.time))
        for bad in ("2026-09-06T12:00:00", "2026-09-06T12:00:00+09:00", "invalidZ"):
            with self.assertRaises(LedgerError):
                utc_timestamp(bad)

    def test_duplicate_answers_and_changed_keys_do_not_duplicate_or_replace_evidence(self):
        self.register(key="register")
        first = self.answer(key="one-attempt")
        control_learning(self.root, self.cfg, "first", "target", candidate_id=self.identity, target="OWN", reason="希望", clock=self.clock)
        count = len(self.events())
        retried = self.answer(key="one-attempt")
        self.assertTrue(retried["duplicate"])
        self.assertEqual(retried["projection_hash"], first["projection_hash"])
        self.assertEqual(len(self.events()), count)
        with self.assertRaises(LedgerError) as error:
            self.command("answer", answers={**self.answers, "principle": "overclaim"}, key="one-attempt")
        self.assertEqual(error.exception.code, "IDEMPOTENCY_CONFLICT")
        with self.assertRaises(LedgerError) as error:
            self.answer(expected_revision=1)
        self.assertEqual(error.exception.code, "REVISION_CONFLICT")

    def test_learning_commands_preserve_the_lease_exception_but_mixed_changes_do_not(self):
        self.register()
        self.answer()
        self.command("schedule", due_at=iso(self.time), reason="復習")
        events = self.events()
        for event in events:
            if event["type"] in EVENT_ACTORS:
                self.assertTrue(is_learning_command(events, event["command_id"]))
        mixed = deepcopy(events)
        mixed[-2]["type"] = "ProposalRecorded"
        self.assertFalse(is_learning_command(mixed, mixed[-1]["command_id"]))

    def test_replay_never_reads_updated_materials_clock_files_or_external_grader(self):
        self.register()
        self.command("schedule", due_at=iso(self.time), reason="反復する")
        self.answer()
        events = self.events()
        expected = projection(replay(events))
        with mock.patch("builtins.open", side_effect=AssertionError("file")), \
             mock.patch("pathlib.Path.open", side_effect=AssertionError("file")), \
             mock.patch("subprocess.run", side_effect=AssertionError("process")), \
             mock.patch("uuid.uuid4", side_effect=AssertionError("random")), \
             mock.patch("time.time", side_effect=AssertionError("clock")), \
             mock.patch("verantyx.application.now", side_effect=AssertionError("clock")), \
             mock.patch("verantyx.learning_materials.builtin_exercise", side_effect=AssertionError("mutable material")), \
             mock.patch("socket.socket", side_effect=AssertionError("network")):
            self.assertEqual(projection(replay(events)), expected)
            self.assertEqual(due_reviews(replay(events), iso(self.time))["total_due"], 0)

    def test_archive_replays_exercises_but_cannot_grant_live_authority(self):
        self.register()
        self.answer()
        self.command("schedule", due_at=iso(self.time), reason="参照する")
        expected = self.item()
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            raw = store.export().encode()
        with tempfile.TemporaryDirectory() as other:
            cfg = config.defaults(Path(other), "ja")
            config.save(Path(other), cfg, None)
            with EventStore(other, cfg["project"]["id"], create=True) as store:
                imported = store.import_archive(raw, iso(self.time))
            view = inspect_exercises(other, cfg, "first", candidate_id=self.identity, exercise_id=self.spec["id"], archive_id=imported["archive_id"])
            self.assertEqual(view["trust"], "ARCHIVE_ONLY")
            self.assertEqual(view["candidate"]["id"], expected["id"])
            self.assertEqual(view["candidate"]["exercises"][0]["exercise_hash"], expected["exercises"][0]["exercise_hash"])
            self.assertEqual(list_learning(other, cfg, "first", imported["archive_id"])["candidates"][0], expected)
            with self.assertRaises(LedgerError) as error:
                control_exercises(other, cfg, "first", "answer", candidate_id=self.identity, exercise_id=self.spec["id"], answers=self.answers)
            self.assertEqual(error.exception.code, "RUN_NOT_FOUND")

    def test_material_view_omits_answer_key_and_all_ui_catalogs_have_equal_keys(self):
        material = inspect_exercises(self.root, self.cfg, "first", candidate_id=self.identity)["material"]
        self.assertEqual(material["exercise_hash"], digest(self.spec))
        self.assertTrue(all("rubric" not in item for item in material["questions"]))
        entries = translation_entries()
        self.assertEqual(set(entries), set(LANGUAGES))
        for locale in LANGUAGES:
            self.assertEqual(set(entries[locale]), set(entries["ja"]))
            value = {"material": public_exercise(builtin_exercise("parallel_writers", locale))}
            output = StringIO()
            with redirect_stdout(output):
                display(value, locale, "learn-material")
            self.assertIn(LABELS[locale]["boundary"], output.getvalue())
            self.assertIn(value["material"]["lesson"]["title"], output.getvalue())

    def test_cli_parser_and_dispatch_register_answer_due_and_cancel_real_ledger(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command")
        register(sub)
        args = parser.parse_args(["learn-exercise-register", "first", "--candidate", self.identity, "--key", "cli-register"])
        result = dispatch(self.root, self.cfg, args, "ja")
        self.assertEqual(len(result["candidates"][0]["exercises"]), 1)
        answers_file = self.root / "answers.json"
        from verantyx.domain.codec import canonical
        answers_file.write_text(canonical(self.answers), encoding="utf-8")
        args = parser.parse_args(["learn-exercise-answer", "first", "--candidate", self.identity, "--exercise", self.spec["id"],
                                 "--answers", str(answers_file), "--key", "cli-answer"])
        result = dispatch(self.root, self.cfg, args, "ja")
        self.assertEqual(result["candidates"][0]["exercises"][0]["assessments"][0]["result"]["status"], "PASSED")
        due = "2099-09-06T12:00:00Z"
        args = parser.parse_args(["learn-review-schedule", "first", "--candidate", self.identity, "--exercise", self.spec["id"],
                                 "--due", due, "--reason", "自分の復習", "--key", "cli-schedule"])
        dispatch(self.root, self.cfg, args, "ja")
        args = parser.parse_args(["learn-due", "first", "--at", due])
        self.assertEqual(dispatch(self.root, self.cfg, args, "ja")["total_due"], 1)
        args = parser.parse_args(["learn-review-cancel", "first", "--candidate", self.identity, "--exercise", self.spec["id"],
                                 "--reason", "必要時に確認", "--key", "cli-cancel"])
        dispatch(self.root, self.cfg, args, "ja")
        args = parser.parse_args(["learn-due", "first", "--at", due])
        self.assertEqual(dispatch(self.root, self.cfg, args, "ja")["total_due"], 0)
        self.assertEqual(set(COMMANDS), set(sub.choices))

    def test_cli_file_reader_rejects_duplicate_answer_keys_without_creating_attempt(self):
        self.register()
        parser = argparse.ArgumentParser()
        register(parser.add_subparsers(dest="command"))
        path = self.root / "ambiguous.json"
        path.write_text('{"principle":"bounded","principle":"overclaim"}', encoding="utf-8")
        args = parser.parse_args(["learn-exercise-answer", "first", "--candidate", self.identity, "--exercise", self.spec["id"],
                                 "--answers", str(path), "--key", "invalid-answer"])
        with self.assertRaises(LedgerError) as error:
            dispatch(self.root, self.cfg, args, "ja")
        self.assertEqual(error.exception.code, "DOCUMENT_INVALID")
        self.assertEqual(len(self.item()["exercises"][0]["attempts"]), 0)


if __name__ == "__main__":
    unittest.main()
