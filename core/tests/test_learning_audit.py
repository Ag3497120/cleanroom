"""Independent adversarial checks for the learning extension's public boundaries."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import json
import os
import subprocess
import sys
import unittest

import test_learning_extended as learning_fixture
from verantyx.application import iso
from verantyx.commands_learning import _document
from verantyx.domain.codec import canonical, digest
from verantyx.domain.events import make_event
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay, projection
from verantyx.learning import control_learning, list_learning
from verantyx.learning_exercises import inspect_exercises, control_exercises
from verantyx.storage.sqlite import EventStore, parse_archive


def keys(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(v) for v in value))
    return set()


class LearningAuditTests(unittest.TestCase):
    def setUp(self):
        self.fx = learning_fixture.LearningExerciseTests()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)

    def test_assessment_comparison_distinguishes_json_booleans_integers_and_floats(self):
        f = self.fx
        f.register()
        f.answer()
        events = f.events()
        index = next(i for i, event in enumerate(events) if event["type"] == "LearningExerciseAssessed")
        for field, value in (("score", 3.0), ("person_authenticated", 0), ("matched", 1)):
            with self.subTest(field=field):
                event = deepcopy(events[index])
                if field == "matched":
                    event["payload"]["result"]["question_results"][0][field] = value
                else:
                    event["payload"]["result"][field] = value
                event["event_hash"] = digest({k: v for k, v in event.items() if k != "event_hash"})
                with self.assertRaises(LedgerError) as error:
                    replay([*events[:index], event])
                self.assertEqual(error.exception.code, "LEARNING_ASSESSMENT_INVALID")

    def test_material_response_omits_rubrics_and_prior_private_answers_but_preserves_history(self):
        f = self.fx
        f.register()
        f.answer(answer_origin={"kind": "UNKNOWN", "identity": "PRIVATE_ANSWER_ORIGIN_84", "model": None, "provider": None})
        control_learning(f.root, f.cfg, "first", "explain", candidate_id=f.identity,
                         statement="PRIVATE_SELF_REPORT_84", clock=f.clock)
        before = projection(replay(f.events()))
        material = inspect_exercises(f.root, f.cfg, "first", candidate_id=f.identity, exercise_id=f.spec["id"])
        self.assertNotIn("rubric", keys(material))
        self.assertNotIn("answers", keys(material))
        self.assertNotIn("PRIVATE_", canonical(material))
        all_material = inspect_exercises(f.root, f.cfg, "first", candidate_id=f.identity)
        self.assertNotIn("rubric", keys(all_material))
        self.assertNotIn("PRIVATE_", canonical(all_material))
        history = list_learning(f.root, f.cfg, "first")
        self.assertIn("PRIVATE_SELF_REPORT_84", canonical(history))
        self.assertIn("rubric", keys(history))
        self.assertEqual(projection(replay(f.events())), before)

    def test_real_cli_material_json_has_no_nested_answer_key(self):
        f = self.fx
        f.register()
        f.answer()
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        result = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(f.root), "--json",
                                 "learn-material", "first", "--candidate", f.identity], capture_output=True, text=True,
                                timeout=5, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertNotIn("rubric", keys(value))
        self.assertNotIn("answers", keys(value))

    def test_document_reader_does_not_follow_symlinks_or_wait_for_a_fifo(self):
        f = self.fx
        target = f.root / "private.json"
        target.write_text('{"secret":"private"}')
        link = f.root / "link.json"
        link.symlink_to(target)
        with self.assertRaises((LedgerError, OSError)):
            _document(link)
        fifo = f.root / "pipe"
        os.mkfifo(fifo)
        code = "from verantyx.commands_learning import _document; import sys\ntry: _document(sys.argv[1])\nexcept Exception: sys.exit(7)\nsys.exit(0)"
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
        result = subprocess.run([sys.executable, "-c", code, str(fifo)], capture_output=True, timeout=2, env=env)
        self.assertEqual(result.returncode, 7)
        large = f.root / "large.json"
        large.write_bytes(b" " * 65537)
        with self.assertRaises(LedgerError) as error:
            _document(large)
        self.assertEqual(error.exception.code, "DOCUMENT_LIMIT")

    def test_early_practice_does_not_complete_or_accelerate_a_future_review(self):
        f = self.fx
        f.register()
        due = iso(f.time + timedelta(days=1))
        f.command("schedule", due_at=due, intervals_days=[1, 3, 7], reason="spaced review")
        for _ in range(3):
            f.answer()
        review = f.item()["exercises"][0]["review"]
        self.assertEqual((review["due_at"], review["step"], review["completed_reviews"]), (due, 0, 0))
        self.assertEqual(len(f.item()["exercises"][0]["assessments"]), 3)
        f.time += timedelta(days=1)
        f.answer()
        review = f.item()["exercises"][0]["review"]
        self.assertEqual((review["step"], review["completed_reviews"]), (1, 1))

    def test_clock_rollback_cannot_reorder_attempts_or_move_review_backwards(self):
        f = self.fx
        f.register()
        f.command("schedule", due_at=iso(f.time), reason="review")
        f.time += timedelta(hours=1)
        f.answer()
        before = len(f.events())
        f.time -= timedelta(minutes=30)
        with self.assertRaises(LedgerError) as error:
            f.answer()
        self.assertEqual(error.exception.code, "LEARNING_REVIEW_TIME")
        self.assertEqual(len(f.events()), before)

    def test_current_off_suppresses_live_due_without_rewriting_task_or_archives(self):
        f = self.fx
        f.register()
        f.command("schedule", due_at=iso(f.time), reason="review")
        original = projection(replay(f.events()))
        with EventStore(f.root, f.cfg["project"]["id"], create=True) as store:
            archive = store.import_archive(store.export().encode(), iso(f.time))
        f.cfg["learning"]["mode"] = "off"
        self.assertEqual(inspect_exercises(f.root, f.cfg, "first", clock=f.clock)["suppressed"], "LEARNING_OFF")
        archived = inspect_exercises(f.root, f.cfg, "first", archive_id=archive["archive_id"], clock=f.clock)
        self.assertEqual(archived["trust"], "ARCHIVE_ONLY")
        self.assertEqual(archived["total_due"], 1)
        self.assertEqual(projection(replay(f.events())), original)

    def test_current_item_limit_applies_to_live_due_list(self):
        f = self.fx
        f.cfg["learning"]["max_items"] = 1
        for index in range(2):
            identity = f.identity if not index else f.candidate("second")
            control_exercises(f.root, f.cfg, "first", "register", candidate_id=identity, document=f.spec, clock=f.clock)
            control_exercises(f.root, f.cfg, "first", "schedule", candidate_id=identity, exercise_id=f.spec["id"],
                              due_at=iso(f.time), reason="review", clock=f.clock)
        result = inspect_exercises(f.root, f.cfg, "first", clock=f.clock)
        self.assertEqual((result["total_due"], len(result["items"])), (2, 1))

    def test_legacy_learning_archive_does_not_require_new_material_or_grader(self):
        f = self.fx
        control_learning(f.root, f.cfg, "first", "explain", candidate_id=f.identity,
                         statement="This is a legacy self report.", clock=f.clock)
        expected = projection(replay(f.events()))
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            raw = store.export().encode()
        with mock.patch("verantyx.learning_exercises.grade", side_effect=AssertionError("new grader for old history")), \
             mock.patch("verantyx.learning_materials.builtin_exercise", side_effect=AssertionError("mutable new lesson")):
            imported = parse_archive(raw)
            self.assertEqual(projection(replay(imported["events"])), expected)
        self.assertEqual(expected["state"]["deltas"]["human_delta"][0]["mastery_assessment"], "NOT_ASSESSED")

    def test_delayed_assessment_cannot_complete_a_deferred_or_new_learning_cycle(self):
        import uuid
        f = self.fx
        f.register()
        f.answer()
        events = f.events()
        attempt_index = next(i for i, e in enumerate(events) if e["type"] == "LearningExerciseAttempted")
        original_result = events[attempt_index + 1]["payload"]
        before = events[:attempt_index + 1]
        base = {"candidate_id": f.identity, "candidate_hash": original_result["candidate_hash"], "reason": "deferred"}
        def append(chain, kind, payload):
            prior = chain[-1]
            event = make_event(f.cfg["project"]["id"], "first", prior["revision"] + 1, str(uuid.uuid4()), iso(f.time),
                               kind, payload, str(uuid.uuid4()), prior)
            return [*chain, event]
        deferred = append(before, "LearningDeferred", base)
        with self.assertRaises(LedgerError) as error:
            replay(append(deferred, "LearningExerciseAssessed", original_result))
        self.assertEqual(error.exception.code, "LEARNING_STAGE")
        resumed = append(deferred, "LearningResumed", {**base, "reason": "resumed"})
        with self.assertRaises(LedgerError) as error:
            replay(append(resumed, "LearningExerciseAssessed", original_result))
        self.assertEqual(error.exception.code, "LEARNING_STAGE")
