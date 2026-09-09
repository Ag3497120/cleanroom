"""Real processes exercise the ordinary hybrid workflow without live models."""
from copy import deepcopy
from pathlib import Path
from unittest import mock
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid

from verantyx import config
from verantyx.application import get_projection, record_run
from verantyx.domain.codec import canonical, digest
from verantyx.domain.events import make_event
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.responses import ask, build_request, compose, validate_response
from verantyx.storage.sqlite import EventStore

SOURCE = Path(__file__).resolve().parents[1] / "src"
ANSWERS = {"ja": "同じ要求を再送しても、反映は一度だけにする設計です。",
           "en": "Apply the change once even when the same request is retried.",
           "zh-Hans": "即使重试同一请求，也只应用一次更改。",
           "ko": "같은 요청을 재시도해도 변경은 한 번만 적용합니다.",
           "es": "Aplica el cambio una sola vez aunque se repita la solicitud."}


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.calls = self.root / "model-calls.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def adapter(self, mutation="", filename="model"):
        script = self.root / (filename + ".py")
        script.write_text(
            "import json,sys\nfrom pathlib import Path\nvalue=json.load(sys.stdin)\n"
            f"with Path({str(self.calls)!r}).open('a') as f: f.write(json.dumps(value)+'\\n')\n"
            f"answers={ANSWERS!r}\n"
            "if value['format']=='verantyx.proposal-request.v1':\n"
            " doc=value['proposal_template']; doc['summary']=answers[value['task']['response_locale']]\n"
            " doc['unknowns']=[{'id':'retry-check','question':'How is a repeated request checked?', 'needed_observation':'a fixed repeated-request check'}]\n"
            "else:\n"
            " doc=value['response_template']; doc['answer']=answers[doc['response_locale']]\n"
            " ref=value['task']['source_ref']\n"
            " if value['max_learning_items']:\n"
            "  doc['learning_candidates']=[{'concept_id':'idempotence','concept':answers[doc['response_locale']],"
            "'why_now':'The current task involves repeated requests.', 'minimum_model':'A retry must not repeat the side effect.',"
            "'counterexample':'Charging twice after a network retry.', 'check':'Design a duplicate request case and its expected count.', 'source_refs':[ref]}]\n"
            " doc['reusable_candidates']=[{'kind':'VERIFICATION_IDEA','title':'Repeated-request check', 'situation':'A request may arrive twice.',"
            "'procedure':'Submit the same key twice and assert one effect.', 'counterexample':'Two charges for one key.', 'source_refs':[ref]}]\n"
            + mutation + "\nprint(json.dumps(doc))\n")
        path = self.root / (filename + ".json")
        path.write_text(json.dumps({"argv": [sys.executable, str(script)]}))
        return path

    def start(self, run_id="test"):
        return record_run(self.root, self.cfg, request="HTTP再試行の設計", run_id=run_id)

    def invocations(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []

    def assert_code(self, code, call, *args, **kwargs):
        with self.assertRaises(LedgerError) as error:
            call(*args, **kwargs)
        self.assertEqual(error.exception.code, code)

    def test_ask_answers_and_collects_real_candidate_in_one_workflow(self):
        adapter = self.adapter()
        result = ask(self.root, self.cfg, request="HTTP再試行の設計", run_id="retry", adapter_path=adapter, key="one")
        state = result["state"]
        self.assertEqual(state["latest_response"]["mode"], "GENERATED")
        self.assertEqual(state["latest_response"]["document"]["answer"], ANSWERS["ja"])
        self.assertEqual(len(self.invocations()), 2)
        self.assertIn("context_assets", self.invocations()[0])
        self.assertEqual(len(state["learning_candidates"]), 1)
        candidate = next(iter(state["learning_candidates"].values()))
        self.assertEqual(candidate["origin"], "EXTERNAL_RESPONSE")
        self.assertTrue(candidate["target_is_suggestion"])
        self.assertEqual(candidate["evidence"], [])
        self.assertEqual(candidate["project_anchor"], state["latest_response"]["source_ref"])
        self.assertEqual(state["human_decisions"], {})
        self.assertEqual(state["effects"], {})
        self.assertFalse(state["can_execute_effects"])
        self.assertEqual(state["deltas"]["human_delta"][0]["mastery_assessment"], "NOT_ASSESSED")

    def test_duplicate_and_replay_never_invoke_model_again(self):
        adapter = self.adapter()
        kwargs = dict(request="retry", run_id="retry", adapter_path=adapter, key="same")
        first = ask(self.root, self.cfg, **kwargs)
        second = ask(self.root, self.cfg, **kwargs)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["projection_hash"], second["projection_hash"])
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("retry")
        with mock.patch("verantyx.adapters.command_process.BoundedProcess", side_effect=AssertionError("replay called model")):
            restored = replay(events)
        self.assertEqual(restored["latest_response"], first["state"]["latest_response"])
        self.assertEqual(len(self.invocations()), 2)

    def test_context_conflict_is_rejected_before_call(self):
        first = self.start()
        self.assert_code("REVISION_CONFLICT", compose, self.root, self.cfg, "test", adapter_path=self.adapter(),
                         key="wrong", expected_revision=first["recorded_revision"] + 1)
        self.assertEqual(self.invocations(), [])

    def test_unknown_source_falls_back_without_capturing_model_candidates(self):
        first = self.start()
        adapter = self.adapter("doc['learning_candidates'][0]['source_refs']=['invented:source']")
        result = compose(self.root, self.cfg, "test", adapter_path=adapter, key="bad", expected_revision=first["recorded_revision"])
        response = result["state"]["latest_response"]
        self.assertEqual(response["mode"], "FALLBACK")
        self.assertEqual(response["generator_error"], "RESPONSE_SOURCE")
        self.assertEqual(result["state"]["learning_candidates"], {})
        self.assertNotIn("invented:source", canonical(response))

    def test_norm_rewrite_and_authority_field_are_rejected(self):
        for index, mutation in enumerate(("doc['norms_sha256']='0'*64", "doc['human_decision']='approved'")):
            first = self.start("bad-" + str(index))
            result = compose(self.root, self.cfg, "bad-" + str(index), adapter_path=self.adapter(mutation), key="bad-" + str(index),
                             expected_revision=first["recorded_revision"])
            self.assertEqual(result["state"]["latest_response"]["mode"], "FALLBACK")
            self.assertEqual(result["state"]["human_decisions"], {})

    def test_all_five_requested_languages_reach_proposal_and_response(self):
        adapter = self.adapter()
        for locale, answer in ANSWERS.items():
            result = ask(self.root, self.cfg, request="retry", run_id="lang-" + locale, adapter_path=adapter, key="lang-" + locale, locale=locale)
            self.assertEqual(result["state"]["latest_response"]["document"]["answer"], answer)
            self.assertEqual(result["state"]["latest_response"]["locale"], locale)
        self.assertEqual(len(self.invocations()), 10)

    def test_learning_off_is_honored_in_generation_and_collection(self):
        self.cfg["learning"]["mode"] = "off"
        result = ask(self.root, self.cfg, request="retry", adapter_path=self.adapter(), key="off")
        self.assertEqual(result["state"]["learning_candidates"], {})
        self.assertEqual(result["state"]["deltas"]["human_delta"], [])
        self.assertEqual(self.invocations()[-1]["max_learning_items"], 0)

    def test_local_response_has_no_model_call_and_is_replayable(self):
        first = self.start()
        result = compose(self.root, self.cfg, "test", key="local", expected_revision=first["recorded_revision"])
        self.assertEqual(result["state"]["latest_response"]["mode"], "FALLBACK")
        self.assertIsNone(result["state"]["latest_response"]["generator_error"])
        self.assertEqual(self.invocations(), [])

    def test_after_response_interruption_resumes_without_duplicate_call(self):
        first = self.start()
        kwargs = dict(adapter_path=self.adapter(), key="resume", expected_revision=first["recorded_revision"])
        def fault(stage):
            if stage == "after_response":
                raise RuntimeError("simulated interruption")
        with self.assertRaises(RuntimeError):
            compose(self.root, self.cfg, "test", **kwargs, fault=fault)
        self.assertEqual(len(self.invocations()), 1)
        result = compose(self.root, self.cfg, "test", **kwargs)
        self.assertEqual(result["state"]["latest_response"]["mode"], "GENERATED")
        self.assertEqual(len(self.invocations()), 1)

    def test_after_started_interruption_does_not_guess_external_outcome(self):
        first = self.start()
        kwargs = dict(adapter_path=self.adapter(), key="uncertain", expected_revision=first["recorded_revision"])
        def fault(stage):
            if stage == "after_started":
                raise RuntimeError("simulated interruption")
        with self.assertRaises(RuntimeError):
            compose(self.root, self.cfg, "test", **kwargs, fault=fault)
        self.assert_code("BRIDGE_OUTCOME_UNKNOWN", compose, self.root, self.cfg, "test", **kwargs)
        self.assertEqual(self.invocations(), [])

    def test_concurrent_project_change_does_not_launch_or_record_stale_answer(self):
        first = self.start()
        def change(_command):
            self.start("other")
        self.assert_code("REVISION_CONFLICT", compose, self.root, self.cfg, "test", adapter_path=self.adapter(),
                         key="race", expected_revision=first["recorded_revision"], before_invoke=change)
        self.assertEqual(self.invocations(), [])

    def test_mutated_recorded_facts_are_rejected_by_replay(self):
        first = self.start()
        compose(self.root, self.cfg, "test", key="local", expected_revision=first["recorded_revision"])
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("test")
        pos = next(i for i, e in enumerate(events) if e["type"] == "ResponseComposed")
        event = events[pos]
        payload = deepcopy(event["payload"])
        payload["facts"]["facts"][0]["text"] = "Everything has been independently proved."
        forged = make_event(event["project_id"], event["stream_id"], event["revision"], event["command_id"], event["recorded_at"],
                            event["type"], payload, event["event_id"], events[pos-1])
        self.assert_code("RESPONSE_CONTEXT", replay, [*events[:pos], forged])

    def test_model_api_accepts_new_protocol_and_rejects_omitted_facts(self):
        from verantyx.model_api import _validate_output, payload
        first = self.start()
        from verantyx.adapters.cross_response import response_route
        request = build_request(first["state"], "ja", {}, response_route(first["state"]))
        document = request["response_template"]
        self.assertEqual(_validate_output(request, document), document)
        for provider in ("openai", "anthropic", "gemini", "ollama"):
            wire = payload({"provider": provider, "model": "fixture", "max_output_tokens": 4000}, request)
            self.assertIn("verantyx.response-request.v1", canonical(wire))
        invalid = deepcopy(document)
        invalid["explanations"] = []
        self.assert_code("RESPONSE_INVALID", validate_response, invalid, request)

    def test_translation_edits_do_not_change_historical_response_or_break_replay(self):
        first = self.start()
        result = compose(self.root, self.cfg, "test", key="local", expected_revision=first["recorded_revision"])
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("test")
        from verantyx.presentation import narrative_facts
        def revised(state, locale):
            facts = narrative_facts(state, locale)
            facts["summary"] = "改訂した表示文"
            for row in facts["facts"]:
                row["text"] = "意味を変えずに読みやすく改訂した表示文"
            return facts
        with mock.patch("verantyx.presentation.narrative_facts", side_effect=revised):
            restored = replay(events)
        self.assertEqual(restored["latest_response"], result["state"]["latest_response"])

    def test_interrupted_response_resumes_from_recorded_prompt_after_translation_edit(self):
        first = self.start()
        kwargs = dict(adapter_path=self.adapter(), key="translate-resume", expected_revision=first["recorded_revision"])
        def fault(stage):
            if stage == "after_response":
                raise RuntimeError("simulated interruption")
        with self.assertRaises(RuntimeError):
            compose(self.root, self.cfg, "test", **kwargs, fault=fault)
        original = self.invocations()[0]
        from verantyx.presentation import narrative_facts
        def revised(state, locale):
            facts = narrative_facts(state, locale)
            facts["summary"] = "変更後の表示"
            for row in facts["facts"]:
                row["text"] = "読みやすさを調整した表示文"
            return facts
        with mock.patch("verantyx.presentation.narrative_facts", side_effect=revised):
            result = compose(self.root, self.cfg, "test", **kwargs)
        self.assertEqual(result["state"]["latest_response"]["request_snapshot"], original)
        self.assertEqual(len(self.invocations()), 1)

    def test_malformed_recorded_fact_shapes_fail_with_a_domain_error(self):
        first = self.start()
        compose(self.root, self.cfg, "test", key="shape", expected_revision=first["recorded_revision"])
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("test")
        pos = next(i for i,e in enumerate(events) if e["type"] == "ResponseComposed")
        event = events[pos]
        for key, value in (("facts", [None]), ("facts", "invalid"), ("next_steps", [False]), ("next_steps", None)):
            payload = deepcopy(event["payload"])
            payload["facts"][key] = value
            payload["request_snapshot"]["norms"] = payload["facts"]
            payload["request_sha256"] = digest(payload["request_snapshot"])
            forged = make_event(event["project_id"], event["stream_id"], event["revision"], event["command_id"], event["recorded_at"],
                                event["type"], payload, event["event_id"], events[pos-1])
            self.assert_code("RESPONSE_CONTEXT", replay, [*events[:pos], forged])
        for field in ("summary", "fact_text", "step_text"):
            payload = deepcopy(event["payload"])
            if field == "summary":
                del payload["facts"]["summary"]
            elif field == "fact_text":
                del payload["facts"]["facts"][0]["text"]
            else:
                del payload["facts"]["next_steps"][0]["text"]
            payload["request_snapshot"]["norms"] = payload["facts"]
            payload["request_sha256"] = digest(payload["request_snapshot"])
            forged = make_event(event["project_id"], event["stream_id"], event["revision"], event["command_id"], event["recorded_at"],
                                event["type"], payload, event["event_id"], events[pos-1])
            self.assert_code("RESPONSE_INVALID", replay, [*events[:pos], forged])

    def test_cli_ask_and_dictionary_are_usable_without_json(self):
        adapter = self.adapter()
        env = {**os.environ, "PYTHONPATH": str(SOURCE)}
        result = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(self.root), "--lang", "ja", "ask", "HTTP再試行",
                                 "--adapter", str(adapter), "--key", "cli", "--task-id", "cli"], text=True, capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(ANSWERS["ja"], result.stdout)
        self.assertNotIn("UNKNOWN", result.stdout)
        result = subprocess.run([sys.executable, "-m", "verantyx", "--project", str(self.root), "--lang", "ja", "dictionary"],
                                text=True, capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(ANSWERS["ja"], result.stdout)


if __name__ == "__main__":
    unittest.main()
