"""Narrative boundaries, translation, factual attribution and ordinary CLI use."""
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest import mock
import io
import json
import os
import string
import subprocess
import sys
import tempfile
import unittest

from verantyx import config
from verantyx.application import record_run
from verantyx.cli import kernel_output
from verantyx.domain.codec import digest
from verantyx.i18n import LANGUAGES, catalog
from verantyx.presentation import (MAX_FACTS, display_reply, fallback_text, gap_text, localized_status,
                                   narrative_facts, render_reply, response_freshness)
from verantyx.storage.sqlite import EventStore

ROOT = Path(__file__).resolve().parents[1]


def state_fixture():
    return {"run_id": "answer-task", "revision": 7, "request": "Explain a retry strategy", "request_ref": "project:request",
            "proposal_ref": "project:proposal", "last_command_id": "previous-command", "command_start_revision": 3,
            "locale": "ja", "latest_observations": {}, "learning_candidates": {},
            "proposal": {"summary": "Wait briefly before trying again.\n\nStop after the configured limit.", "response_locale": "en",
                         "decision_points": []},
            "assessment": {"strategy": "UNKNOWN", "evidence": "UNKNOWN", "ownership": "UNASSESSED", "build": "IN_PROGRESS",
                           "claims": [], "actions": [], "judgments": [], "question": None,
                           "gaps": [{"code": "MISSING_SOURCE", "item_id": "retry", "source_ref": "project:proposal",
                                     "classification": "UNKNOWN_EVIDENCE", "epistemic_status": "UNKNOWN"}]}}


def with_response(state, locale="en", mode="GENERATED"):
    value = deepcopy(state)
    basis = state["revision"]
    facts = narrative_facts(state, locale)
    document = {"answer": "A generated explanation of retry intervals.",
                "explanations": [{"fact_id": item["id"], "text": item["text"]} for item in facts["facts"]]}
    response = {"document": document, "facts": facts, "basis_revision": basis, "recorded_revision": basis + 1,
                "command_id": "response-command", "proposal_ref": state.get("proposal_ref"), "locale": locale,
                "source_ref": "project:response", "mode": mode}
    value.update(revision=basis + 2, command_start_revision=basis, last_command_id="response-command", latest_response=response)
    return value


class PresentationFactsTests(unittest.TestCase):
    def test_facts_are_pure_and_ids_are_stable_across_languages(self):
        state = state_fixture()
        before = deepcopy(state)
        expected = narrative_facts(state, "ja")
        with mock.patch("builtins.open", side_effect=AssertionError("unexpected file access")), \
                mock.patch("pathlib.Path.read_text", side_effect=AssertionError("unexpected file access")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("unexpected process")), \
                mock.patch("time.time", side_effect=AssertionError("unexpected clock")):
            for locale in LANGUAGES:
                first = narrative_facts(state, locale)
                self.assertEqual(first, narrative_facts(state, locale))
                self.assertEqual([item["id"] for item in first["facts"]], [item["id"] for item in expected["facts"]])
                self.assertEqual(first["facts"][0]["code"], "UNKNOWN")
                self.assertNotIn("UNKNOWN", fallback_text(state, locale))
        self.assertEqual(before, state)

    def test_projection_metadata_does_not_change_replayable_facts(self):
        state = state_fixture()
        projected = {**state, "rights": {"can_execute": False}, "replay_only": True,
                     "trust": "LOCAL_HISTORY", "historical_assessment": True, "can_execute_effects": False}
        self.assertEqual(narrative_facts(state, "ja"), narrative_facts(projected, "ja"))
        projected["trust"] = "ARCHIVE_ONLY"
        self.assertEqual(narrative_facts(state, "ja"), narrative_facts(projected, "ja"))
        self.assertIn(catalog("ja")["presentation.archive"], render_reply(projected, "ja"))

    def test_missing_stale_conflicted_and_refuted_results_have_different_explanations(self):
        state = state_fixture()
        cases = {"MISSING_SOURCE": "open", "STALE_SOURCE": "stale", "SOURCE_CHANGED": "stale",
                 "PROPERTY_REFUTED": "refuted", "VERIFICATION_CONFLICT": "contested",
                 "AUTHORITY_REQUIRED": "permission", "VALUE_DECISION_REQUIRED": "decision",
                 "EXECUTION_OUTCOME_UNKNOWN": "uncertain_execution"}
        for code, situation in cases.items():
            item = deepcopy(state)
            item["assessment"]["gaps"] = [{"code": code, "source_ref": "project:evidence", "classification":
                                           "CONTESTED" if code == "VERIFICATION_CONFLICT" else "UNKNOWN_EVIDENCE"}]
            for locale in LANGUAGES:
                facts = narrative_facts(item, locale)
                self.assertEqual(facts["summary"], catalog(locale)["presentation.summary." + situation])
                reason = next(row for row in facts["facts"] if row["category"] == "gap")
                self.assertEqual(reason["source_refs"], ["project:evidence"])
                self.assertEqual(reason["code"], code)
                self.assertNotIn(code, reason["text"])

    def test_property_failure_does_not_refute_the_associated_prose(self):
        state = state_fixture()
        state["assessment"]["claims"] = [{"id": "retry-count", "epistemic_status": "UNKNOWN", "prose_entailment": "NOT_ASSESSED",
                                          "property_evidence": {"epistemic_status": "REFUTED", "closure": "REFUTED",
                                                                "scope": "FIXED_TARGET_AND_PREDICATES_ONLY",
                                                                "current_evidence_refs": ["project:failed-check"]}}]
        facts = narrative_facts(state, "ja")
        failed = next(item for item in facts["facts"] if item["category"] == "property_evidence")
        self.assertEqual(failed["code"], "REFUTED")
        self.assertIn("project:failed-check", failed["source_refs"])
        self.assertIn("文章全体の真偽を判定したものではありません", failed["text"])
        self.assertEqual(state["assessment"]["claims"][0]["epistemic_status"], "UNKNOWN")
        self.assertNotIn("REFUTED", render_reply(state, "ja"))

    def test_no_proposal_does_not_describe_a_nonexistent_answer(self):
        state = state_fixture()
        state["proposal"] = None
        state["proposal_ref"] = None
        for locale in LANGUAGES:
            rendered = render_reply(state, locale)
            self.assertIn(catalog(locale)["presentation.evidence_no_proposal"], rendered)
            self.assertNotIn(catalog(locale)["presentation.evidence_without_checks"], rendered)

    def test_reused_rule_names_the_actual_choice_and_pending_choice_remains_pending(self):
        state = state_fixture()
        state["proposal"]["decision_points"] = [{"id": "retry", "options": [{"id": "bounded", "label": "上限付きの再試行"}]}]
        judgment = {"point_id": "retry", "kind": "VALUE_DECISION", "question": "再試行の回数はどうしますか？",
                    "status": "PRECEDENT_MATCHED", "choice": "bounded", "rule_refs": ["project:rule"]}
        state["assessment"]["judgments"] = [judgment]
        facts = narrative_facts(state, "ja")
        reused = next(row for row in facts["facts"] if row["category"] == "judgment")
        self.assertIn("上限付きの再試行", reused["text"])
        self.assertIn("今回もう一度選ぶ必要がありません", reused["text"])
        self.assertEqual(reused["source_refs"], ["project:rule"])
        judgment.update(status="UNDECIDED_HUMAN", choice=None, rule_refs=[])
        waiting = next(row for row in narrative_facts(state, "ja")["facts"] if row["category"] == "judgment")
        self.assertIn("利用者の選択を待っています", waiting["text"])
        self.assertNotIn("PRECEDENT_MATCHED", render_reply(state, "ja"))

    def test_learning_target_and_self_report_never_become_mastery(self):
        state = state_fixture()
        state["learning_candidates"] = {"candidate": {"ownership_target": "OWN", "evidence": []}}
        facts = narrative_facts(state, "ja")
        ownership = next(item for item in facts["facts"] if item["category"] == "ownership")
        self.assertEqual(ownership["details"]["mastery_evidence"], "NONE")
        state["learning_candidates"]["candidate"]["evidence"] = [{"kind": "SelfExplanationSubmitted", "source_ref": "project:self-report"}]
        ownership = next(item for item in narrative_facts(state, "ja")["facts"] if item["category"] == "ownership")
        self.assertEqual(ownership["details"]["mastery_evidence"], "SELF_REPORTED")
        self.assertEqual(ownership["details"]["mastery_assessment"], "NOT_ASSESSED")
        self.assertIn("習熟を認定する評価ではなく", ownership["text"])
        self.assertEqual(state["assessment"]["ownership"], "UNASSESSED")

    def test_rule_advisory_keeps_its_actual_localized_enforcement_visible(self):
        state = state_fixture()
        state["assessment"]["judgments"] = [{"point_id": "retry", "status": "UNDECIDED_HUMAN", "kind": "VALUE_DECISION",
                                             "advisories": [{"outcome": "MATCH", "enforcement": "WARN", "rule_ref": "project:rule"}]}]
        for locale in LANGUAGES:
            rendered = render_reply(state, locale)
            self.assertIn(catalog(locale)["presentation.enforcement.WARN"], rendered)
            self.assertIn(catalog(locale)["presentation.rule_warning"], rendered)
            self.assertNotIn("WARN", rendered)

    def test_bounded_facts_keep_late_failures_and_disclose_omissions(self):
        state = state_fixture()
        state["assessment"]["gaps"] = [{"code": "MISSING_SOURCE", "item_id": "item-" + str(index), "source_ref": "project:proposal"}
                                       for index in range(100)]
        state["assessment"]["gaps"].append({"code": "PROPERTY_REFUTED", "item_id": "late-failure", "source_ref": "project:failed"})
        facts = narrative_facts(state, "ja")
        self.assertEqual(len(facts["facts"]), MAX_FACTS)
        self.assertGreater(facts["omitted_count"], 0)
        self.assertTrue(any(item["code"] == "PROPERTY_REFUTED" for item in facts["facts"]))
        self.assertIn("省略しています", fallback_text(state, "ja"))
        self.assertLessEqual(len(fallback_text(state, "ja")), 16000)

    def test_unknown_future_codes_keep_the_code_without_leaking_it_into_default_prose(self):
        state = state_fixture()
        state["assessment"]["gaps"] = [{"code": "FUTURE_KERNEL_CODE", "source_ref": "project:future"}]
        self.assertEqual(gap_text(state["assessment"]["gaps"][0], "ja"), catalog("ja")["presentation.gap_unknown"])
        self.assertNotIn("FUTURE_KERNEL_CODE", render_reply(state, "ja"))
        detailed = render_reply(state, "ja", include_codes=True, include_sources=True)
        self.assertIn("FUTURE_KERNEL_CODE", detailed)
        self.assertIn("project:future", detailed)

    def test_all_added_translations_are_nonempty_and_have_matching_placeholders(self):
        formatter = string.Formatter()
        reference = {key: value for key, value in catalog("en").items() if key.startswith("presentation.")}
        for locale in LANGUAGES:
            translated = {key: value for key, value in catalog(locale).items() if key.startswith("presentation.")}
            self.assertEqual(set(reference), set(translated))
            for key, value in reference.items():
                self.assertTrue(translated[key].strip())
                fields = lambda text: {field for _, field, _, _ in formatter.parse(text) if field}
                self.assertEqual(fields(value), fields(translated[key]), key)
            for code in ("UNKNOWN", "REFUTED", "CONTESTED", "BOUNDED", "OUTCOME_UNKNOWN", "PLANNED", "COMPLETED"):
                self.assertNotIn(code, localized_status(code, locale, domain="verification"))


class GeneratedReplyDisplayTests(unittest.TestCase):
    def test_current_generated_body_and_attributed_explanation_keep_fixed_facts_visible(self):
        state = with_response(state_fixture())
        explanation = state["latest_response"]["document"]["explanations"][1]
        explanation["text"] = "Everything is verified and you have mastered it."
        before = deepcopy(state)
        rendered = render_reply(state, "en")
        self.assertEqual(response_freshness(state, "en"), "CURRENT")
        self.assertIn("A generated explanation of retry intervals.", rendered)
        self.assertIn(catalog("en")["presentation.generated_explanations"], rendered)
        self.assertIn(catalog("en")["presentation.evidence_without_checks"], rendered)
        self.assertIn(catalog("en")["presentation.ownership_unassessed"], rendered)
        self.assertEqual(before, state)

    def test_old_basis_different_proposal_and_language_do_not_appear_as_a_current_answer(self):
        original = with_response(state_fixture())
        for change, expected in (({"last_command_id": "next-command", "revision": 12}, "HISTORICAL"),
                                 ({"proposal_ref": "project:next-proposal"}, "HISTORICAL"),
                                 ({"command_start_revision": 2}, "HISTORICAL")):
            state = {**deepcopy(original), **change}
            self.assertEqual(response_freshness(state, "en"), expected)
            self.assertNotIn("A generated explanation of retry intervals.", render_reply(state, "en"))
            self.assertIn(catalog("en")["presentation.response_historical"], render_reply(state, "en"))
        self.assertEqual(response_freshness(original, "es"), "OTHER_LOCALE")
        self.assertNotIn("A generated explanation of retry intervals.", render_reply(original, "es"))
        self.assertIn(catalog("es")["presentation.response_other_locale"], render_reply(original, "es"))

    def test_new_learning_suggestions_in_the_response_command_do_not_make_it_stale(self):
        state = with_response(state_fixture())
        state["learning_candidates"]["new"] = {"status": "OPEN", "ownership_target": "REVIEW", "evidence": []}
        state["revision"] += 2
        self.assertEqual(response_freshness(state, "en"), "CURRENT")

    def test_changed_facts_with_the_same_command_are_detected(self):
        state = with_response(state_fixture())
        state["assessment"]["gaps"].append({"code": "PROPERTY_REFUTED", "source_ref": "project:failed"})
        self.assertEqual(response_freshness(state, "en"), "CONTEXT_CHANGED")
        self.assertNotIn("A generated explanation of retry intervals.", render_reply(state, "en"))

    def test_translated_wording_changes_do_not_change_recorded_meaning(self):
        state = with_response(state_fixture())
        facts = state["latest_response"]["facts"]
        facts["summary"] = "Earlier summary wording."
        for row in [*facts["facts"], *facts["next_steps"]]:
            row["text"] = "Earlier localized wording."
        self.assertEqual(response_freshness(state, "en"), "CURRENT")
        facts["facts"][1]["details"]["prose_entailment"] = "SUPPORTED"
        self.assertEqual(response_freshness(state, "en"), "CONTEXT_CHANGED")

    def test_failed_generation_is_visible_and_unknown_error_codes_are_not_exposed(self):
        for locale in LANGUAGES:
            state = with_response(state_fixture(), locale, mode="FALLBACK")
            state["latest_response"]["generator_error"] = "PROPOSAL_CONTEXT"
            rendered = render_reply(state, locale)
            self.assertIn(catalog(locale)["presentation.generator_failed"], rendered)
            self.assertIn(catalog(locale)["error.PROPOSAL_CONTEXT"], rendered)
            self.assertNotIn("PROPOSAL_CONTEXT", rendered)
            state["latest_response"]["generator_error"] = "FUTURE_GENERATOR_FAILURE"
            rendered = render_reply(state, locale)
            self.assertIn(catalog(locale)["presentation.generator_failed"], rendered)
            self.assertNotIn("FUTURE_GENERATOR_FAILURE", rendered)
            state["latest_response"]["generator_error"] = None
            self.assertNotIn(catalog(locale)["presentation.generator_failed"], render_reply(state, locale))

    def test_multiline_answers_are_readable_and_terminal_controls_are_inert(self):
        state = state_fixture()
        state["proposal"]["summary"] = "First paragraph.\n\nSecond paragraph.\x1b[2J\u202ehidden"
        rendered = render_reply(state, "en")
        self.assertIn("First paragraph.\n\nSecond paragraph.", rendered)
        self.assertNotIn("\x1b", rendered)
        self.assertNotIn("\u202e", rendered)
        self.assertIn("\\u001b[2J\\u202ehidden", rendered)

    def test_json_output_retains_the_exact_machine_document(self):
        state = with_response(state_fixture())
        result = {"schema_version": 1, "ok": True, "state": state}
        before = deepcopy(result)
        output = io.StringIO()
        with redirect_stdout(output):
            kernel_output(result, "ja", True, "propose")
        self.assertEqual(json.loads(output.getvalue()), before)
        self.assertEqual(result, before)
        self.assertEqual(json.loads(output.getvalue())["state"]["assessment"]["evidence"], "UNKNOWN")


class ActualPresentationFlowTests(unittest.TestCase):
    def test_ordinary_cli_replay_displays_saved_answer_in_all_five_locales_without_writing_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cfg = config.defaults(root, "ja")
            config.save(root, cfg, None)
            proposal = {"schema_version": 1, "task_id": "visible", "context_revision": 0, "response_locale": "ja",
                        "summary": "試行回数に上限を設けます。\n\n一時的な失敗に限って再試行します。", "claims": [], "actions": [], "unknowns": []}
            path = root / "proposal.json"
            path.write_text(json.dumps(proposal))
            record_run(root, cfg, request="再試行を説明する", run_id="visible", proposal_path=path)
            with EventStore(root, cfg["project"]["id"]) as store:
                expected_events = digest(store.events())
            for locale in LANGUAGES:
                process = subprocess.run([sys.executable, str(ROOT / "bin/verantyx"), "--project", str(root),
                                          "--lang", locale, "replay", "visible"], capture_output=True, text=True,
                                         env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, timeout=10)
                self.assertEqual(process.returncode, 0, process.stderr)
                self.assertIn(proposal["summary"], process.stdout)
                self.assertIn(catalog(locale)["presentation.recorded_facts"], process.stdout)
                self.assertNotIn("UNKNOWN", process.stdout)
            with EventStore(root, cfg["project"]["id"]) as store:
                self.assertEqual(expected_events, digest(store.events()))

    def test_actual_failed_verification_has_localized_scope_and_preserves_unknown_prose_status(self):
        import test_verification
        fixture = test_verification.VerificationTests("runTest")
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        wrong = deepcopy(fixture.spec)
        wrong["checks"][0]["expected"] = 41
        planned = fixture.plan(wrong)
        result = fixture.run_check(planned["verification_id"])
        self.assertEqual(result["verification"]["receipt"]["result"]["closure"], "REFUTED")
        self.assertEqual(result["state"]["assessment"]["claims"][0]["epistemic_status"], "UNKNOWN")
        before = deepcopy(result)
        for locale in LANGUAGES:
            output = io.StringIO()
            with redirect_stdout(output):
                kernel_output(result, locale, False, "verify-run")
            self.assertIn(catalog(locale)["presentation.verification.REFUTED"], output.getvalue())
            self.assertIn(result["verification"]["receipt_ref"], output.getvalue())
            self.assertNotIn("REFUTED", output.getvalue())
            self.assertNotIn("UNKNOWN", output.getvalue())
        self.assertEqual(result, before)


if __name__ == "__main__":
    unittest.main()
