"""Behavior contracts for Work / Reflection / Authority, without live AI calls."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import hashlib
import json
import sys
import uuid

from verantyx import config
from verantyx import agent_runtime as runtime
from verantyx.agent_models import selected_work, select_reflection
from verantyx.agent_projection import owner_projection
from verantyx.agent_schema import WORK_REQUEST, REFLECTION_REQUEST, native_contract
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore


def work(answer="Useful answer", tools=(), status="COMPLETE", question=""):
    return {"format": "verantyx.work-proposal.v1", "status": status, "answer": answer,
            "tool_requests": list(tools), "owner_question": question, "assumptions": []}


def tool(name, path="", text="", identifier="tool-1"):
    return {"id": identifier, "tool": name, "path": path, "text": text}


def reflection(request, text="A project-specific principle", kind="REVIEW"):
    source = request["trace"]["events"][0]["source_ref"]
    return {"format": "verantyx.reflection-proposal.v1", "owner_items": [
        {"kind": kind, "text": text, "reason": "Supported by the selected work record.",
         "source_event_ids": [source], "minimum_model": "Explain the boundary.",
         "counterexample": "A claim without a receipt.", "understanding_check": "Identify the missing evidence."}
    ]}


class Planes(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = {"schema_version": 1, "project": {"id": str(uuid.uuid4()), "name": "Notebook", "purpose": "Retain ownership"},
                    "ui": {"locale": "ja"}, "learning": {"mode": "digest", "max_items": 2},
                    "runtime": {"backend": "none"}, "telemetry": {"enabled": False}}
        config.save(self.root, self.cfg, None)
        self.adapter = self.root / "fake-model.json"
        self.adapter.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(99)"]}))
        self.identity = {"provider": "controlled_fixture", "model": "fixture",
                         "adapter_sha256": hashlib.sha256(self.adapter.read_bytes()).hexdigest()}
        self.calls = []

    def model(self, value):
        return {"document": value, "model": deepcopy(self.identity)}

    def run_agent(self, request="Develop the requested artifact.", key=None, **kwargs):
        from verantyx.development import run_work
        return run_work(self.root, self.cfg, request=request, key=key or uuid.uuid4().hex,
                        work_adapter=str(self.adapter), **kwargs)

    def state(self, run_id):
        return runtime._state(self.root, self.cfg, run_id)

    def events(self, run_id):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events(run_id)

    def test_reflection_failure_preserves_answer_and_candidate_before_call(self):
        def call(root, adapter, request, **kwargs):
            if request["format"] == REFLECTION_REQUEST:
                recorded = self.state(request["run_id"])
                self.assertEqual(recorded["work_result"]["status"], "SUCCEEDED")
                self.assertEqual(recorded["work_result"]["answer"], "Implementation candidate is ready.")
                raise LedgerError("BRIDGE_TIMEOUT")
            if not request["turns"]:
                return self.model(work("Preparing candidate", [tool("write_candidate", "index.html", "<h1>Candidate</h1>")], "CONTINUE"))
            return self.model(work("Implementation candidate is ready."))
        with mock.patch.object(runtime, "invoke", side_effect=call):
            result = self.run_agent()
        self.assertTrue(result["ok"])
        self.assertEqual(result["work"]["status"], "SUCCEEDED")
        self.assertEqual(result["reflection"]["status"], "FAILED")
        self.assertFalse((self.root / "index.html").exists())
        artifact = result["work"]["artifacts"][0]
        self.assertEqual((self.root / artifact["storage_path"]).read_text(), "<h1>Candidate</h1>")
        kinds = [row["type"] for row in self.events(result["run_id"])]
        self.assertLess(kinds.index("WorkResultRecorded"), kinds.index("ReflectionRecorded"))
        self.assertEqual(owner_projection(self.state(result["run_id"]))["evidence_and_unknowns"]["test_receipts"], [])

    def test_short_paraphrases_and_json_word_do_not_select_host_semantics(self):
        def call(root, adapter, request, **kwargs):
            self.calls.append(request["format"])
            return self.model(work("Here is the requested response.") if request["format"] == WORK_REQUEST else
                              {"format": "verantyx.reflection-proposal.v1", "owner_items": []})
        with mock.patch.object(runtime, "invoke", side_effect=call), \
                mock.patch("verantyx.constitution.prepare", side_effect=AssertionError("legacy semantic gate called")):
            for request in ("これを整理して", "JSONという形式でこのAjax課題を整理して", "同じ課題の要点を文章でまとめて"):
                result = self.run_agent(request)
                self.assertTrue(result["ok"])
                self.assertEqual(owner_projection(result["state"])["human_learning_delta"], [])
                self.assertEqual(len(result["state"]["work_turns"]), 1)
        self.assertEqual(self.calls, [WORK_REQUEST, REFLECTION_REQUEST] * 3)

    def test_reorganize_with_different_model_appends_without_repeating_work(self):
        def call(root, adapter, request, **kwargs):
            self.calls.append(request["format"])
            if request["format"] == WORK_REQUEST:
                return self.model(work("The original answer"))
            return self.model(reflection(request, text="Perspective " + str(len(self.calls))))
        other = self.root / "other-model.json"
        other.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(98)"]}))
        with mock.patch.object(runtime, "invoke", side_effect=call):
            first = self.run_agent(key="original")
            organized = runtime.organize(self.root, self.cfg, first["run_id"], adapter=str(other), key="alternative")
            retried = self.run_agent(key="original")
        state = organized["state"]
        self.assertEqual(state["work_result"]["answer"], "The original answer")
        self.assertEqual(len(state["work_reflections"]), 2)
        self.assertNotEqual(state["work_reflections"][0]["proposal"], state["work_reflections"][1]["proposal"])
        self.assertEqual(state["work_reflections"][0]["trace_sha256"], state["work_reflections"][1]["trace_sha256"])
        self.assertEqual(self.calls.count(WORK_REQUEST), 1)
        self.assertEqual(self.calls.count(REFLECTION_REQUEST), 2)
        self.assertTrue(retried["ok"])

    def test_reflection_cannot_activate_rule(self):
        def call(root, adapter, request, **kwargs):
            if request["format"] == WORK_REQUEST:
                return self.model(work())
            output = reflection(request, kind="RULE_CANDIDATE")
            output["owner_items"][0]["status"] = "ACTIVE"
            return self.model(output)
        with mock.patch.object(runtime, "invoke", side_effect=call):
            result = self.run_agent()
        self.assertTrue(result["ok"])
        self.assertEqual(result["reflection"]["status"], "FAILED")
        self.assertNotIn("RuleActivated", [row["type"] for row in self.events(result["run_id"])])

    def test_unknown_source_is_rejected_not_saved_as_candidate(self):
        def call(root, adapter, request, **kwargs):
            if request["format"] == WORK_REQUEST:
                return self.model(work())
            output = reflection(request)
            output["owner_items"][0]["source_event_ids"] = ["invented-event"]
            return self.model(output)
        with mock.patch.object(runtime, "invoke", side_effect=call):
            result = self.run_agent()
        self.assertEqual(result["reflection"]["failure_code"], "REFLECTION_SOURCE_UNKNOWN")
        self.assertEqual(owner_projection(result["state"])["owner_items"], [])
        self.assertTrue(result["ok"])

    def test_human_decision_requires_real_human_event(self):
        def call(root, adapter, request, **kwargs):
            return self.model(work() if request["format"] == WORK_REQUEST else
                              reflection(request, kind="HUMAN_DECISION"))
        with mock.patch.object(runtime, "invoke", side_effect=call):
            result = self.run_agent()
        self.assertEqual(result["reflection"]["failure_code"], "REFLECTION_HUMAN_SOURCE_REQUIRED")
        self.assertEqual(result["state"]["human_decisions"], {})

    def test_scope_is_checked_before_any_model_call(self):
        with mock.patch.object(runtime, "invoke") as call:
            with self.assertRaises(LedgerError) as raised:
                self.run_agent(include=[str(self.root.parent / "outside.txt")])
        self.assertEqual(raised.exception.code, "PATH_SCOPE")
        call.assert_not_called()

    def test_shell_delete_and_outside_candidate_are_refused(self):
        protected = self.root / "keep.txt"
        protected.write_text("Keep this file")
        def call(root, adapter, request, **kwargs):
            if request["format"] == REFLECTION_REQUEST:
                return self.model({"format": "verantyx.reflection-proposal.v1", "owner_items": []})
            if not request["turns"]:
                return self.model(work("Proposing operations", [
                    tool("delete_file", "keep.txt", identifier="delete"),
                    tool("shell", "", "rm keep.txt", identifier="shell"),
                    tool("write_candidate", "../outside.txt", "escape", identifier="escape")], "CONTINUE"))
            return self.model(work("Those operations were refused."))
        with mock.patch.object(runtime, "invoke", side_effect=call):
            result = self.run_agent()
        self.assertEqual(protected.read_text(), "Keep this file")
        self.assertEqual(result["work"]["status"], "PARTIAL")
        self.assertEqual(result["work"]["tool_counts"]["refused"], 3)
        self.assertEqual(result["work"]["artifacts"], [])

    def test_same_work_model_needs_no_reviewer_file(self):
        profile = self.root / ".verantyx/model-adapters/chosen"
        profile.mkdir(parents=True)
        creator = profile / "implementation.json"
        creator.write_bytes(self.adapter.read_bytes())
        self.cfg["runtime"]["model_selection"] = {
            "format": "verantyx.model-selection.v1", "kind": "model_api", "label": "One selected model",
            "creator_adapter": ".verantyx/model-adapters/chosen/implementation.json",
            "reviewer_adapter": ".verantyx/model-adapters/chosen/verification.json",
        }
        config.validate(self.cfg)
        self.assertEqual(selected_work(self.root, self.cfg), str(creator.resolve()))
        self.assertFalse((profile / "verification.json").exists())

    def test_reflection_off_saves_only_work_facts(self):
        select_reflection(self.root, self.cfg, "off")
        with mock.patch.object(runtime, "invoke", return_value=self.model(work())) as call:
            result = self.run_agent()
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["reflection"]["status"], "OFF")
        self.assertEqual(owner_projection(result["state"])["owner_items"], [])

    def test_read_receipt_is_actual_and_next_work_reuses_recorded_context(self):
        (self.root / "source.txt").write_text("Observed project data")
        def call(root, adapter, request, **kwargs):
            if request["format"] == REFLECTION_REQUEST:
                return self.model(reflection(request))
            if request["request"] == "First" and not request["turns"]:
                return self.model(work("Read the source", [tool("read_file", "source.txt")], "CONTINUE"))
            if request["request"] == "First":
                self.assertEqual(request["tool_receipts"][0]["text"], "Observed project data")
            else:
                self.assertTrue(request["project_context"]["reference_only"])
                self.assertEqual(request["project_context"]["prior_work"][0]["reflection_revisions"][0]["authority"], "PROPOSAL_ONLY")
            return self.model(work("Recorded answer"))
        with mock.patch.object(runtime, "invoke", side_effect=call):
            first = self.run_agent("First", include=["source.txt"])
            second = self.run_agent("Next")
        self.assertEqual(owner_projection(first["state"])["recorded_facts"]["file_reads"], 1)
        self.assertTrue(second["ok"])

    def test_owner_question_and_actual_reply_do_not_grant_tool_rights(self):
        def call(root, adapter, request, **kwargs):
            if request["format"] == REFLECTION_REQUEST:
                return self.model({"format": "verantyx.reflection-proposal.v1", "owner_items": []})
            if request["request"] == "First":
                return self.model(work("Two tradeoffs remain", status="NEEDS_OWNER", question="Keep compatibility?"))
            return self.model(work("Keep compatibility in the proposal."))
        with mock.patch.object(runtime, "invoke", side_effect=call):
            first = self.run_agent("First")
            second = self.run_agent("Keep compatibility", continue_from=first["run_id"])
        previous = self.state(first["run_id"])
        self.assertEqual(previous["work_owner_reply"]["text"], "Keep compatibility")
        self.assertEqual(previous["human_decisions"], {})
        self.assertEqual(second["state"]["read_scope"], [])
        self.assertTrue(second["ok"])

    def test_codex_and_ollama_native_schemas_accept_new_work_shape(self):
        from verantyx.codex_wire import validate_envelope
        from verantyx.ollama_schema import output_schema
        from jsonschema import Draft202012Validator
        request = {"format": WORK_REQUEST, "output_contract": "Work"}
        _, envelope = native_contract(request)
        output = work("A normal answer")
        self.assertEqual(validate_envelope({"document": output}, envelope, editor=False), output)
        self.assertTrue(Draft202012Validator(output_schema(request)).is_valid(output))

    def test_owner_choice_and_private_note_survive_next_work_and_reorganization(self):
        from verantyx import owner_experience as owner
        from verantyx.development_console import _mutate
        from verantyx.domain.codec import canonical
        def call(root, adapter, request, **kwargs):
            if request['format'] == REFLECTION_REQUEST:
                return self.model(reflection(request, text='A project-linked principle'))
            if request['request'] == 'Next with retained ownership':
                context = request['project_context']['owner_experience']
                self.assertNotIn('PRIVATE-NOTE-TEST', canonical(request))
                self.assertIn('SHARED-DESIGN-TEST', canonical(context))
                self.assertEqual(context['ownership_choices'][0]['target'], 'DELEGATE')
                self.assertEqual(context['ownership_choices'][0]['authority'],
                                 'LEARNING_PREFERENCE_NOT_EXECUTION_PERMISSION')
                self.assertEqual(context['human_mastery'], 'NOT_ASSESSED')
            return self.model(work('Recorded work answer'))
        with mock.patch.object(runtime, 'invoke', side_effect=call):
            first = self.run_agent('Synthetic owner test fixture')
            item = owner.cards(first['state'])[0]
            _mutate(self.root, self.cfg, owner.choose, first['run_id'], item['reference'],
                    'SELECT_TARGET', target='DELEGATE', reason='Synthetic test selection')
            _mutate(self.root, self.cfg, owner.add_note, first['run_id'],
                    reference=item['reference'], text='PRIVATE-NOTE-TEST', share_with_ai=False)
            _mutate(self.root, self.cfg, owner.decide, first['run_id'],
                    statement='SHARED-DESIGN-TEST', reason='Synthetic fixture, not user testimony')
            second = self.run_agent('Next with retained ownership')
            organized = runtime.organize(self.root, self.cfg, first['run_id'],
                                         adapter=str(self.adapter), key='later-interpretation')
        original = next(row for row in owner.cards(organized['state']) if row['reference'] == item['reference'])
        self.assertEqual(original['target'], 'DELEGATE')
        self.assertFalse(original['target_is_suggestion'])
        self.assertEqual(original['human_notes'][0]['text'], 'PRIVATE-NOTE-TEST')
        self.assertEqual(original['human_understanding'], 'NOT_ASSESSED')
        self.assertTrue(second['ok'])
        self.assertFalse(owner.project(owner.read_states(self.root, self.cfg), self.cfg)['writes'])

    def test_timeout_keeps_incrementally_saved_files_and_does_not_repeat_work(self):
        def call(root, adapter, request, **kwargs):
            if request['format'] == REFLECTION_REQUEST:
                return self.model({'format': 'verantyx.reflection-proposal.v1', 'owner_items': []})
            if not request['turns']:
                return self.model(work('Saved part one', [tool('write_candidate', 'part.txt', 'Persisted')], 'CONTINUE'))
            raise LedgerError('BRIDGE_TIMEOUT')
        with mock.patch.object(runtime, 'invoke', side_effect=call) as model:
            first = self.run_agent(key='interrupted')
            calls = model.call_count
            second = self.run_agent(key='interrupted')
        self.assertEqual(first['work']['status'], 'PARTIAL')
        self.assertEqual(first['work']['reason'], 'BRIDGE_TIMEOUT')
        self.assertEqual(second['work'], first['work'])
        self.assertEqual(model.call_count, calls)
        artifact = first['work']['artifacts'][0]
        self.assertEqual((self.root / artifact['storage_path']).read_text(), 'Persisted')
        self.assertFalse((self.root / 'part.txt').exists())

    def test_continuation_keeps_old_files_and_reads_their_recorded_versions(self):
        def call(root, adapter, request, **kwargs):
            if request['format'] == REFLECTION_REQUEST:
                return self.model({'format': 'verantyx.reflection-proposal.v1', 'owner_items': []})
            if request['request'] == 'Create':
                return self.model(work('Created', [
                    tool('write_candidate', 'index.html', 'v1', 'html'),
                    tool('write_candidate', 'style.css', 'kept', 'css')]))
            if not request['turns']:
                self.assertEqual({row['path'] for row in request['candidate_manifest']}, {'index.html', 'style.css'})
                return self.model(work('Read previous candidate', [tool('read_candidate', 'index.html')], 'CONTINUE'))
            self.assertEqual(request['tool_receipts'][0]['text'], 'v1')
            return self.model(work('Updated', [tool('write_candidate', 'index.html', 'v2')]))
        with mock.patch.object(runtime, 'invoke', side_effect=call):
            first = self.run_agent('Create')
            second = self.run_agent('Update', continue_from=first['run_id'])
        self.assertTrue(second['ok'])
        folder = self.root / second['work']['artifact_directory']
        self.assertEqual((folder / 'index.html').read_text(), 'v2')
        self.assertEqual((folder / 'style.css').read_text(), 'kept')
        old = self.root / first['work']['artifact_directory']
        self.assertEqual((old / 'index.html').read_text(), 'v1')
        self.assertFalse((self.root / 'index.html').exists())

    def test_opaque_asset_copy_is_scoped_and_never_sent_as_model_text(self):
        from verantyx.domain.codec import canonical
        raw = b'OPAQUE_ASSET_CONTENT' * 5000
        (self.root / 'dependency.bin').write_bytes(raw)
        def call(root, adapter, request, **kwargs):
            self.assertNotIn('OPAQUE_ASSET_CONTENT', canonical(request))
            if request['format'] == REFLECTION_REQUEST:
                return self.model({'format': 'verantyx.reflection-proposal.v1', 'owner_items': []})
            return self.model(work('Copied the approved bytes', [
                tool('copy_asset', 'vendor/dependency.bin', 'dependency.bin')]))
        with mock.patch.object(runtime, 'invoke', side_effect=call):
            result = self.run_agent(assets=['dependency.bin'])
        self.assertTrue(result['ok'])
        artifact = result['work']['artifacts'][0]
        self.assertEqual(artifact['sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual((self.root / result['work']['artifact_directory'] / 'vendor/dependency.bin').read_bytes(), raw)

    def test_changed_asset_is_refused_and_not_promoted(self):
        (self.root / 'dependency.bin').write_bytes(b'original')
        def call(root, adapter, request, **kwargs):
            if request['format'] == REFLECTION_REQUEST:
                return self.model({'format': 'verantyx.reflection-proposal.v1', 'owner_items': []})
            (self.root / 'dependency.bin').write_bytes(b'changed')
            return self.model(work('Attempt copy', [tool('copy_asset', 'vendor/item.bin', 'dependency.bin')]))
        with mock.patch.object(runtime, 'invoke', side_effect=call):
            result = self.run_agent(assets=['dependency.bin'])
        self.assertEqual(result['work']['status'], 'PARTIAL')
        self.assertEqual(result['work']['artifacts'], [])
        self.assertEqual(result['state']['work_tools'][0]['reason'], 'WORK_CANDIDATE_CHANGED')
