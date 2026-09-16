"""Freedom in meaning, exact provenance, and diagnosable model failures."""
from copy import deepcopy
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import json
import sys

from verantyx.agent_schema import (REFLECTION_REQUEST, WORK_REQUEST, generation_schema,
                                   schema, validate_output)
from verantyx.errors import LedgerError
from verantyx.model_api import payload
from verantyx.model_observation import diagnostic, emit, parse


class FlexibleModelContract(TestCase):
    def request(self):
        return {"format": REFLECTION_REQUEST, "trace": {"events": [
            {"source_ref": "project:event-a", "type": "WorkTurnRecorded"},
            {"source_ref": "project:event-b", "type": "WorkToolRecorded"}]},
            "output_contract": "Organize useful interpretations", "response_locale": "ja"}

    def connection(self):
        return {"provider": "ollama", "model": "fixture", "endpoint": "http://127.0.0.1:11434/api/chat",
                "max_output_tokens": 4096, "thinking": False}

    def proposal(self, text):
        return {"format": "verantyx.reflection-proposal.v1", "owner_items": [
            {"kind": "REVIEW", "text": text, "reason": "A supported perspective",
             "source_event_ids": ["project:event-a"], "minimum_model": "",
             "counterexample": "", "understanding_check": ""}]}

    def test_generation_limits_source_ids_not_interpretations(self):
        request = self.request()
        generated = generation_schema(request)
        item = generated["properties"]["owner_items"]["items"]["properties"]
        self.assertEqual(item["source_event_ids"]["items"]["enum"], ["project:event-a", "project:event-b"])
        self.assertNotIn("enum", item["text"])
        self.assertEqual(item["kind"], schema(request)["properties"]["owner_items"]["items"]["properties"]["kind"])
        for text in ("State transitions matter here", "Accessible feedback is the useful principle"):
            self.assertEqual(validate_output(request, self.proposal(text))["owner_items"][0]["text"], text)

    def test_unknown_source_keeps_specific_host_error(self):
        document = self.proposal("A plausible but unsupported interpretation")
        document["owner_items"][0]["source_event_ids"] = ["not-real"]
        with self.assertRaises(LedgerError) as error:
            validate_output(self.request(), document)
        self.assertEqual(error.exception.code, "REFLECTION_SOURCE_UNKNOWN")

    def test_empty_trace_allows_only_empty_generation(self):
        value = {**self.request(), "trace": {"events": []}}
        self.assertEqual(generation_schema(value)["properties"]["owner_items"]["maxItems"], 0)
        validate_output(value, {"format": "verantyx.reflection-proposal.v1", "owner_items": []})

    def test_normal_work_and_reflection_use_model_sampling_defaults(self):
        for value in (self.request(), {"format": WORK_REQUEST, "request": "Make something useful"}):
            encoded = payload(self.connection(), value)
            self.assertNotIn("temperature", encoded["options"])
            actual = json.loads(encoded["messages"][1]["content"])
            self.assertEqual(actual, value)
            self.assertNotIn("answer_instruction", actual)
            self.assertNotIn("leave actions empty", encoded["messages"][0]["content"])

    def test_legacy_adapters_are_not_silently_reconfigured(self):
        value = {"format": "verantyx.learning-request.v1"}
        self.assertEqual(payload(self.connection(), value)["options"]["temperature"], 0)

    def test_provenance_error_survives_the_bounded_diagnostic_channel(self):
        out = StringIO()
        emit(out, {"kind": "error", **diagnostic(LedgerError("REFLECTION_SOURCE_UNKNOWN",
                                            {"provider_body": "private", "api_key": "secret"}))})
        event = parse(out.getvalue().strip().encode())
        self.assertEqual(event["code"], "REFLECTION_SOURCE_UNKNOWN")
        self.assertEqual(event["details"], {})
        self.assertNotIn("secret", out.getvalue())

    def test_failure_replay_keeps_safe_details_without_second_call(self):
        from verantyx.agent_models import invoke
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".verantyx").mkdir(mode=0o700)
            adapter = root / "adapter.json"
            adapter.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(97)"]}))
            with mock.patch("verantyx.agent_models.BoundedProcess") as process:
                process.return_value.__enter__.return_value.document.side_effect = LedgerError(
                    "BRIDGE_TIMEOUT", {"reason": "MODEL_API_TIMEOUT", "provider_body": "private"})
                for _ in range(2):
                    with self.assertRaises(LedgerError) as error:
                        invoke(root, str(adapter), self.request(), key="one-failed-call")
                    self.assertEqual(error.exception.details.get("reason"), "MODEL_API_TIMEOUT")
                self.assertEqual(process.call_count, 1)
