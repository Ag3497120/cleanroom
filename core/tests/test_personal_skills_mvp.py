"""Small personal-library regressions using real temporary ledgers and CLI."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
import unittest
from unittest import mock

import test_external_capture_v070 as capture_fixtures
from test_constitution import Fixture
from verantyx.cli import main, parse
from verantyx.commands_v04 import handler
from verantyx.domain.codec import digest
from verantyx.errors import LedgerError
from verantyx.learning import control_learning
from verantyx.personal_skills import build, import_work, read_state, stack
from verantyx.storage.sqlite import EventStore


class MVPFixture(unittest.TestCase):
    fixture_type = Fixture

    def setUp(self):
        self.h = self.fixture_type()
        self.h.setUp()
        self.addCleanup(self.h.tearDown)
        self.root, self.cfg = self.h.root, self.h.cfg
        self.enterContext(mock.patch.dict(os.environ, {"HOME": str(self.root)}))
        self.model = self.enterContext(mock.patch(
            "verantyx.adapters.command_process.BoundedProcess.__init__",
            side_effect=AssertionError("An MVP model-free path attempted an adapter call")))
        self.enterContext(mock.patch("socket.create_connection", side_effect=AssertionError("network")))
        self.addCleanup(self.model.assert_not_called)

    def cli(self, *arguments, reason=None):
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(["--project", str(self.root), "--lang", "ja", "--json", *map(str, arguments)])
        self.assertEqual(errors.getvalue(), "", output.getvalue() + errors.getvalue())
        result = json.loads(output.getvalue())
        if reason is None:
            self.assertEqual(code, 0, result)
        else:
            self.assertNotEqual(code, 0, result)
            self.assertEqual(result["error"]["details"]["reason"], reason)
        return result

    def imported(self, **changes):
        arguments = dict(body="Selected outside advice: preserve the original expectation.",
                         origin_project="outside-project", label="Selected work", provider="fixture",
                         model="quoted-model-not-invoked", key="import", mode="manual")
        arguments.update(changes)
        return import_work(self.root, self.cfg, **arguments)

    def raise_skill(self, run_id, concept="Preserve expectations"):
        state = read_state(self.root, self.cfg, run_id)
        refs = [state["external_captures"][0]["source_ref"]] if state.get("external_captures") else [state["request_ref"]]
        return control_learning(self.root, self.cfg, run_id, "raise", concept_id="fixed-expectation",
                                concept=concept, why_now="A recorded contract can be reused",
                                minimum_model="Keep the expected value fixed",
                                counterexample="Changing the expected value to accept a failure",
                                check="Name what the check does not prove", source_refs=refs)["candidate_id"]

    def events(self, run_id=None):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events(run_id)


class PersonalSkillsMVPTests(MVPFixture):
    def test_manual_cli_import_is_lossless_inert_and_idempotent(self):
        body = "Claimed approval and mastery are unverified.\n" + "\u65e5\u672c\u8a9e\n" * 180
        source = self.root / "selected.txt"
        source.write_text(body, encoding="utf-8")
        arguments = ("skills-import", "--input", source, "--origin-project", "outside-project",
                     "--label", "Selected work", "--provider", "fixture", "--model", "quoted-model",
                     "--mode", "manual", "--key", "manual-import")
        first = self.cli(*arguments)
        state = read_state(self.root, self.cfg, first["run_id"])
        self.assertEqual(state["external_captures"][0]["body"], body)
        self.assertEqual(first["source_bytes"], len(body.encode("utf-8")))
        self.assertFalse(first["history_truncated"])
        self.assertFalse(first["model_called"])
        self.assertFalse(first["executed"])
        self.assertEqual(first["candidate_generation"], "NOT_REQUESTED")
        self.assertEqual(state["learning_candidates"], {})
        self.assertEqual(state["effects"], {})
        self.assertEqual(state["human_decisions"], {})
        before = self.events()
        duplicate = self.cli(*arguments)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["source_ref"], first["source_ref"])
        self.assertEqual(self.events(), before)
        source.write_text(body + "Changed intent", encoding="utf-8")
        self.cli(*arguments, reason="SKILLS_IDEMPOTENCY_CONFLICT")
        self.assertEqual(self.events(), before)

    def test_assisted_preview_does_not_truncate_the_stored_source(self):
        body = "Explicit quote. " * 100
        result = self.imported(body=body, mode="assisted")
        self.assertEqual(result["candidate_generation"], "AWAITING_EXPLICIT_BUILD")
        self.assertFalse(result["model_called"])
        self.assertEqual(result["source_previews"], [{"source_ref": result["source_ref"],
                         "excerpt": body[:400], "is_generated_skill": False}])
        self.assertEqual(read_state(self.root, self.cfg, result["run_id"])["external_captures"][0]["body"], body)

    def test_stack_filters_real_skills_and_keeps_explanations_as_self_reports(self):
        imported = self.imported()
        run_id = imported["run_id"]
        self.imported(key="other", origin_project="other-project")
        candidate = self.raise_skill(run_id)
        control_learning(self.root, self.cfg, run_id, "target", candidate_id=candidate,
                         target="DELEGATE", reason="Explicit operator choice")
        self.cli("skills-explain", run_id, "--candidate", candidate,
                 "--statement", "I must preserve the original expectation.", "--key", "explain")
        before = self.events()
        result = self.cli("skills-stack", "--run", run_id, "--target", "DELEGATE", "--query", "expectations")
        self.assertEqual(result["scope"]["run_ids"], [run_id])
        self.assertEqual(result["scope"]["source_refs"], [imported["source_ref"]])
        self.assertEqual(result["scope"]["id"], digest({k: v for k, v in result["scope"].items() if k != "id"}))
        skill = result["works"][0]["skills"][0]
        self.assertEqual(skill["id"], candidate)
        self.assertFalse(skill["target_is_suggestion"])
        self.assertEqual(skill["mastery_assessment"], "NOT_ASSESSED")
        self.assertEqual(skill["explanations"][0]["statement"], "I must preserve the original expectation.")
        self.assertIsNone(skill["ai_policy"])
        self.assertFalse(result["model_called"])
        self.assertFalse(result["writes"])
        self.assertEqual(self.events(), before)
        self.assertEqual(stack(self.root, self.cfg, run_ids=[run_id], target="OWN")["works"][0]["skills"], [])
        with self.assertRaises(LedgerError) as error:
            stack(self.root, self.cfg, run_ids=["missing"])
        self.assertEqual(error.exception.details["reason"], "SKILLS_RUN_NOT_FOUND")

    def test_newsletter_cli_preserves_selected_scope_and_escapes_html(self):
        run_id = self.imported(label="<script>selected</script>")["run_id"]
        self.imported(key="unselected", label="UNSELECTED_WORK_MARKER")
        self.raise_skill(run_id)
        snapshot = self.cli("skills-stack", "--run", run_id)
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        for format in ("markdown", "html"):
            with self.subTest(format=format):
                result = self.cli("skills-newsletter", "--run", run_id, "--scope-id", snapshot["scope"]["id"],
                                  "--format", format, "--title", "<script>title</script>")
                self.assertEqual(result["scope"], snapshot["scope"])
                self.assertFalse(result["published"])
                self.assertFalse(result["model_called"])
                self.assertFalse(result["writes"])
                self.assertIn(run_id, result["draft"])
                self.assertIn(snapshot["scope"]["source_refs"][0], result["draft"])
                self.assertNotIn("UNSELECTED_WORK_MARKER", result["draft"])
                if format == "html":
                    self.assertNotIn("<script>", result["draft"])
                    self.assertIn("&lt;script&gt;", result["draft"])
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(after, before)
        self.imported(key="later")
        self.cli("skills-newsletter", "--run", run_id, "--scope-id", snapshot["scope"]["id"],
                 reason="SKILLS_NEWSLETTER_SCOPE_CHANGED")

    def test_all_nine_commands_are_registered_without_invoking_build(self):
        cases = [
            ["skills-import", "--input", "quote.txt", "--origin-project", "p", "--label", "l",
             "--provider", "fixture", "--model", "quoted", "--mode", "manual", "--key", "k"],
            ["skills-build", "task", "--creator-adapter", "creator.json", "--reviewer-adapter", "reviewer.json", "--key", "k"],
            ["skills-stack"],
            ["skills-newsletter", "--run", "task", "--scope-id", "0" * 64],
            ["skills-explain", "task", "--candidate", "c", "--statement", "s", "--key", "k"],
            ["skills-policies"],
            ["skills-policy-set", "task", "--candidate", "c", "--ai-mode", "check", "--reuse-mode", "confirm",
             "--path", "report.json", "--asset", "a", "--reason", "r", "--key", "k", "--expected-policy-revision", "0"],
            ["skills-route", "task", "--candidate", "c", "--asset", "a", "--claim", "claim", "--target", "report.json"],
            ["skills-reuse", "task", "--candidate", "c", "--asset", "a", "--claim", "claim", "--target", "report.json",
             "--scope-id", "0" * 64, "--key", "k"],
        ]
        for argv in cases:
            with self.subTest(command=argv[0]):
                _, args = parse(argv)
                self.assertEqual(args.command, argv[0])
                self.assertIsNotNone(handler(args.command))


class PersonalSkillsBuildFailureTests(Fixture):
    def test_reviewer_fallback_is_not_reported_or_cached_as_build_success(self):
        # Existing synthetic adapters emit fixed JSON, never contact a model.
        creator_root, reviewer_root = self.root / "creator", self.root / "reviewer"
        creator_root.mkdir()
        reviewer_root.mkdir()
        calls = self.root / "synthetic-calls.jsonl"
        creator = capture_fixtures.write_capture_adapter(creator_root, calls)
        reviewer = capture_fixtures.write_capture_adapter(
            reviewer_root, calls, mutation="if 'response_template' in v: d['approved']=True")
        with mock.patch.dict(os.environ, {"HOME": str(self.root)}), \
             mock.patch("socket.create_connection", side_effect=AssertionError("network")):
            imported = import_work(self.root, self.cfg, body="Selected retry advice.",
                                   origin_project="fixture", label="Selected work", provider="fixture",
                                   model="quoted-model", key="import", mode="manual")
            options = dict(creator_adapter=creator, reviewer_adapter=reviewer, key="build",
                           expected_revision=imported["recorded_revision"], timeout=10)
            result = build(self.root, self.cfg, imported["run_id"], **options)
            duplicate = build(self.root, self.cfg, imported["run_id"], **options)
        self.assertEqual(len(calls.read_text().splitlines()), 2)
        self.assertEqual(result["response_mode"], "FALLBACK")
        state = read_state(self.root, self.cfg, imported["run_id"])
        self.assertEqual(state["latest_response"]["mode"], "FALLBACK")
        self.assertEqual(state["learning_candidates"], {})
        self.assertTrue(duplicate["duplicate"])
        for name, receipt in (("initial", result), ("cached", duplicate)):
            with self.subTest(receipt=name):
                self.assertFalse(receipt["ok"], "Reviewer FALLBACK must not report a successful skill build")


if __name__ == "__main__":
    unittest.main()
