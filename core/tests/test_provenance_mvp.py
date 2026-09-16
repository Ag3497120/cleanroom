"""Acceptance boundaries, not golden answers or domain-keyword classifiers."""
from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import json
import sys
import uuid

from verantyx import config
from verantyx import agent_runtime as runtime
from verantyx.agent_projection import owner_projection
from verantyx.agent_schema import WORK_REQUEST, REFLECTION_REQUEST
from verantyx.domain.codec import canonical
from verantyx.errors import LedgerError
from verantyx.work_checks import run_check
from test_work_ownership_planes import work, tool, reflection


class ProvenanceMVP(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = {"schema_version": 1,
                    "project": {"id": str(uuid.uuid4()), "name": "Release fixture", "purpose": "Human ownership"},
                    "ui": {"locale": "ja"}, "learning": {"mode": "digest", "max_items": 2},
                    "runtime": {"backend": "none"}, "telemetry": {"enabled": False}}
        config.save(self.root, self.cfg, None)
        self.adapter = self.root / "fixture-adapter.json"
        self.adapter.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(97)"]}))
        from verantyx.agent_models import identity
        self.model = identity(self.adapter)
        self.requests = []

    def respond(self, root, adapter, request, **kwargs):
        self.requests.append(deepcopy(request))
        if request["format"] == REFLECTION_REQUEST:
            document = reflection(request, text="A useful interpretation")
        else:
            document = work("Candidate ready", [tool("write_candidate", "main.py", "print('candidate-ok')\n")])
        return {"document": document, "model": deepcopy(self.model)}

    def create(self, **kwargs):
        return runtime.run_work(self.root, self.cfg, request="Build the requested example",
                                work_adapter=str(self.adapter), reflection_adapter=str(self.adapter),
                                key=uuid.uuid4().hex, **kwargs)

    def test_new_generation_identity_not_same_answer_is_the_contract(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
            second = runtime.organize(self.root, self.cfg, first["run_id"],
                                      adapter=str(self.adapter), key="new-interpretation")
            replayed = runtime.organize(self.root, self.cfg, first["run_id"],
                                        adapter=str(self.adapter), key="new-interpretation")
        generations = [row["generation_id"] for row in self.requests if row["format"] == REFLECTION_REQUEST]
        self.assertEqual(len(generations), 2)
        self.assertNotEqual(*generations)
        self.assertEqual(second["work"], first["work"])
        self.assertEqual(second["reflection"]["proposal"], first["reflection"]["proposal"])
        self.assertTrue(replayed["replayed"])
        # Identical useful answers are allowed; they simply are not forced by cache.

    def test_perspective_is_free_text_and_bound_to_the_revision(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
            result = runtime.organize(self.root, self.cfg, first["run_id"], adapter=str(self.adapter),
                                      perspective="A surprising but grounded perspective", key="lens")
            with self.assertRaises(LedgerError) as raised:
                runtime.organize(self.root, self.cfg, first["run_id"], adapter=str(self.adapter),
                                 perspective="Different request", key="lens")
        self.assertEqual(result["reflection"]["perspective"], "A surprising but grounded perspective")
        self.assertEqual(self.requests[-1]["perspective"], "A surprising but grounded perspective")
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_CONFLICT")

    def test_unselected_old_perspectives_remain_browsable(self):
        from verantyx.owner_experience import cards
        from verantyx.provenance import perspectives
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
            result = runtime.organize(self.root, self.cfg, first["run_id"],
                                      adapter=str(self.adapter), key="another-view")
        self.assertEqual(len(cards(result["state"])), 1)
        self.assertEqual(len(cards(result["state"], include_archived=True)), 2)
        self.assertEqual(len(perspectives(result["state"])), 2)

    def test_reorganization_reads_current_shared_choices_not_private_notes(self):
        from verantyx import owner_experience as owner
        from verantyx.development_console import _mutate
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
            card = owner.cards(first["state"])[0]
            _mutate(self.root, self.cfg, owner.choose, first["run_id"], card["reference"],
                    "SELECT_TARGET", target="REFERENCE")
            _mutate(self.root, self.cfg, owner.add_note, first["run_id"], text="PRIVATE-MVP-NOTE",
                    share_with_ai=False)
            _mutate(self.root, self.cfg, owner.add_note, first["run_id"], text="SHARED-MVP-NOTE",
                    share_with_ai=True)
            result = runtime.organize(self.root, self.cfg, first["run_id"],
                                      adapter=str(self.adapter), key="updated-owner-context")
        sent = canonical(self.requests[-1])
        self.assertNotIn("PRIVATE-MVP-NOTE", sent)
        self.assertIn("SHARED-MVP-NOTE", sent)
        choices = result["reflection"]["owner_context"]["ownership_choices"]
        self.assertEqual(choices[0]["target"], "REFERENCE")
        self.assertEqual(result["work"], first["work"])

    def test_check_requires_explicit_permission(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        with mock.patch("verantyx.work_checks.subprocess.Popen") as process:
            with self.assertRaises(LedgerError) as raised:
                run_check(self.root, self.cfg, first["run_id"], argv=[sys.executable, "main.py"])
        self.assertEqual(raised.exception.code, "CHECK_CONFIRMATION_REQUIRED")
        process.assert_not_called()

    def test_real_check_receipt_and_replay_do_not_change_work(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        checked = run_check(self.root, self.cfg, first["run_id"], argv=[sys.executable, "main.py"],
                            confirmed=True, key="once", label="Run candidate")
        again = run_check(self.root, self.cfg, first["run_id"], argv=[sys.executable, "main.py"],
                          confirmed=True, key="once", label="Run candidate")
        self.assertEqual(checked["check"]["stdout"].strip(), "candidate-ok")
        self.assertEqual(checked["check"]["exit_code"], 0)
        self.assertEqual(checked["check"]["status"], "PASSED")
        self.assertTrue(again["replayed"])
        self.assertEqual(first["work"], checked["state"]["work_result"])
        view = owner_projection(checked["state"])
        self.assertEqual(view["recorded_facts"]["tests_run"], 1)
        self.assertEqual(view["evidence_and_unknowns"]["evidence"], "RECORDED_CHECKS_PASSED")
        self.assertEqual(view["evidence_and_unknowns"]["ownership"], "UNCONFIRMED")
        self.assertFalse((self.root / "main.py").exists())

    def test_failed_check_is_a_fact_not_a_failed_work_or_mastery(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        result = run_check(self.root, self.cfg, first["run_id"],
                           argv=[sys.executable, "-c", "import sys; print('failure'); sys.exit(7)"],
                           confirmed=True, key="failing")
        self.assertFalse(result["ok"])
        self.assertEqual(result["check"]["status"], "FAILED")
        self.assertEqual(result["check"]["exit_code"], 7)
        self.assertEqual(result["state"]["work_result"]["status"], "SUCCEEDED")

    def test_timeout_is_not_a_pass_and_is_not_reexecuted(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        args = dict(argv=[sys.executable, "-c", "import time; time.sleep(30)"],
                    timeout=1, confirmed=True, key="deadline")
        result = run_check(self.root, self.cfg, first["run_id"], **args)
        again = run_check(self.root, self.cfg, first["run_id"], **args)
        self.assertEqual(result["check"]["status"], "TIMED_OUT")
        self.assertIsNone(result["check"]["exit_code"])
        self.assertTrue(again["replayed"])

    def test_check_output_is_bounded_without_hiding_exit_status(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        result = run_check(self.root, self.cfg, first["run_id"], confirmed=True,
                           argv=[sys.executable, "-c", "import sys; print('x'*100000); sys.stderr.write('y'*100000)"])
        self.assertTrue(result["check"]["output_truncated"])
        self.assertEqual(result["check"]["status"], "PASSED")
        self.assertLessEqual(len(result["check"]["stdout"]), 16000)

    def test_check_uses_copy_and_does_not_inherit_api_credentials(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        code = ("import os,pathlib; assert 'OPENAI_API_KEY' not in os.environ; "
                "pathlib.Path('main.py').write_text('changed'); print('copy-only')")
        with mock.patch.dict("os.environ", {"OPENAI_API_KEY": "SYNTHETIC-SECRET"}):
            result = run_check(self.root, self.cfg, first["run_id"], argv=[sys.executable, "-c", code], confirmed=True)
        self.assertEqual(result["check"]["status"], "PASSED")
        artifact = first["work"]["artifacts"][0]
        self.assertEqual((self.root / artifact["storage_path"]).read_text(), "print('candidate-ok')\n")

    def test_checks_enter_new_reflection_as_sources_not_prior_ai_claims(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
            checked = run_check(self.root, self.cfg, first["run_id"],
                                argv=[sys.executable, "main.py"], confirmed=True)
            organized = runtime.organize(self.root, self.cfg, first["run_id"],
                                        adapter=str(self.adapter), key="after-check")
        types = [row["type"] for row in self.requests[-1]["trace"]["events"]]
        self.assertIn("WorkCheckRecorded", types)
        self.assertNotIn("ReflectionRecorded", types)
        self.assertIn(checked["check"]["source_ref"], organized["reflection"]["source_event_ids"])

    def test_corrupted_candidate_is_not_executed(self):
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        artifact = first["work"]["artifacts"][0]
        (self.root / artifact["storage_path"]).write_text("tampered")
        with mock.patch("verantyx.work_checks.subprocess.Popen") as process:
            with self.assertRaises(LedgerError) as raised:
                run_check(self.root, self.cfg, first["run_id"], argv=[sys.executable, "main.py"], confirmed=True)
        self.assertEqual(raised.exception.code, "WORK_CANDIDATE_CHANGED")
        process.assert_not_called()

    def test_current_work_ownership_command_is_renderable(self):
        from verantyx.cli import main
        with mock.patch.object(runtime, "invoke", side_effect=self.respond):
            first = self.create()
        output = StringIO()
        with redirect_stdout(output):
            code = main(["--project", str(self.root), "ownership", first["run_id"]])
        self.assertEqual(code, 0)
        self.assertIn("OWNER", output.getvalue())

    def test_native_provider_failure_is_not_a_task_classification(self):
        from verantyx.codex_cli import _provider_failure
        error = _provider_failure({"message": json.dumps({"status": 400, "error": {
            "message": "The 'some-model' model is not supported when using Codex with a ChatGPT account."}})})
        self.assertEqual(error.details["reason"], "CODEX_MODEL_UNAVAILABLE")
        self.assertEqual(error.code, "BRIDGE_PROCESS_FAILED")

    def test_codex_cache_is_keyed_by_generation_not_forced_agreement(self):
        from verantyx import codex_budget
        from verantyx.codex_cli import configuration
        directory = self.root / "codex-profile"
        cfg = configuration(directory, "implementation", executable=sys.executable)
        codex_budget.initialize(cfg["budget_directory"])
        first = codex_budget.reserve(cfg, {"format": REFLECTION_REQUEST, "generation_id": "first"})
        codex_budget.finish(cfg["budget_directory"], first["id"], status="SUCCEEDED", output={"x": 1})
        second = codex_budget.reserve(cfg, {"format": REFLECTION_REQUEST, "generation_id": "second"})
        self.assertNotEqual(first["id"], second["id"])
        replayed = codex_budget.reserve(cfg, {"format": REFLECTION_REQUEST, "generation_id": "first"})
        self.assertEqual(replayed["id"], first["id"])
