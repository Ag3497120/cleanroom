"""Bounded acceptance tests; fixtures do not claim real-model teaching quality."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import os
import subprocess
import sys
import threading
import uuid

from verantyx import config
from verantyx import agent_runtime as runtime
from verantyx import learning_capture as capture
from verantyx import learning_guides as guides
from verantyx import personal_profile as profile
from verantyx import sandbox_backends as sandbox
from verantyx import work_harness
from verantyx.agent_schema import PERSONAL_REQUEST, validate_output
from verantyx.domain.codec import canonical, digest
from verantyx.errors import LedgerError


# This transport fixture is intentionally not an LLM or an isolation engine.
FIXTURE = r'''
import json, sys
request = json.loads(sys.stdin.readline())
if request.get("mode") == "unpack":
    if request["target"].get("technology") == "InvalidGuide":
        print(json.dumps({"invalid": True}))
        raise SystemExit()
    ref = request["trace"]["events"][0]["source_ref"]
    resources = request.get("web_search", {}).get("results", [])
    document = {
        "format": "verantyx.learning-guide.v1",
        "title": "Understand the implementation boundary",
        "summary": "A short entry point, not a mastery claim.",
        "starting_point": "Use the owner's explicit experience only.",
        "profile_refs": [],
        "parts": [{
            "title": "The omitted intermediate step",
            "kind": "OMITTED_STEP", "basis": "ADDITIONAL_EXPLANATION",
            "explanation": "Keep input parsing separate from the effect and retain its receipt.",
            "why_for_this_work": "The saved work includes a candidate write.",
            "exercise": "Explain the input and output boundary in your own words.",
            "check": "Identify what was proposed and what actually ran.",
            "next_small_step": "Try this only when you want to.",
            "source_event_ids": [ref]
        }],
        "can_delegate": [{"text": "Repetitive formatting", "source_event_ids": [ref]}],
        "next_opportunity": "Revisit this in a later related project.",
        "gaps": ["The fixture does not prove teaching quality."],
        "resources": ([{"resource_id": resources[0]["id"], "why": "Read the source",
                        "suggested_focus": "The input boundary"}] if resources else []),
        "suggested_searches": []
    }
    print(json.dumps(document))
else:
    first = not request.get("turns")
    note = {
        "title": "Keep the boundary explicit", "target_kind": "BOTH",
        "technology_tags": [request["request"]],
        "explanation": "The original explanation before the final summary.",
        "prerequisites": ["Know which input belongs to this operation."],
        "expanded_steps": ["Receive input.", "Create a candidate.", "Keep the actual receipt."],
        "alternatives": ["Do not substitute a summary for the original event."],
        "pitfalls": ["A proposed check is not a completed check."],
        "verification": ["Inspect the recorded result, not the model's confidence."],
        "next_small_step": "Explain one boundary next time.",
        "source_event_ids": [], "profile_refs": []
    }
    document = {
        "format": "verantyx.work-proposal.v1",
        "status": "CONTINUE" if first else "COMPLETE",
        "answer": "Creating the candidate." if first else "Candidate ready.",
        "owner_question": "", "assumptions": [],
        "tool_requests": ([{"id": "write-1", "tool": "write_candidate",
                           "path": "example.txt", "text": "original candidate contents\n"}] if first else []),
        "learning_notes": "malformed optional note" if request["request"] == "Malformed" else [note]
    }
    print(json.dumps(document))
'''


def seed_project(directory):
    base = Path(directory).resolve()
    root = base / "project"
    root.mkdir(parents=True)
    adapter = root / ".verantyx/model-adapters/fixture/implementation.json"
    adapter.parent.mkdir(parents=True)
    adapter.write_text(json.dumps({"argv": [sys.executable, "-c", FIXTURE]}), encoding="utf-8")
    configuration = {
        "schema_version": 1,
        "project": {"id": str(uuid.uuid4()), "name": "Learning fixture", "purpose": "Retain experience"},
        "ui": {"locale": "ja"}, "learning": {"mode": "digest", "max_items": 1},
        "runtime": {
            "backend": "none",
            "reflection": {"mode": "off", "adapter": None, "label": "Off"},
            "model_selection": {
                "format": "verantyx.model-selection.v1", "kind": "model_api", "label": "Fixture",
                "creator_adapter": ".verantyx/model-adapters/fixture/implementation.json",
                "reviewer_adapter": ".verantyx/model-adapters/fixture/verification.json",
            },
        },
        "telemetry": {"enabled": False},
    }
    config.save(root, configuration, None)
    return root, configuration, adapter


class LearningContinuity(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(prefix="cleanroom-learning-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.environment = mock.patch.dict(os.environ, {
            "VERANTYX_PERSONAL_HOME": str(self.base / "personal"),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.root, self.cfg, self.adapter = seed_project(self.base)
        profile.configure({"enabled": True, "share_with_ai": True, "onboarded": True})

    def work(self, topic="Flask", **kwargs):
        return runtime.run_work(self.root, self.cfg, request=topic,
                                key=uuid.uuid4().hex, max_turns=3, timeout=10, **kwargs)

    def guide(self, topic="Flask", **kwargs):
        return guides.create(self.root, self.cfg, technology=topic,
                             adapter=str(self.adapter), send=True, timeout=10, **kwargs)

    def test_capture_retains_intermediate_explanation_and_actual_candidate(self):
        result = self.work()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["work"]["status"], "SUCCEEDED")
        self.assertEqual(result["reflection"]["status"], "OFF")
        rows = capture.traces()
        types = [row["event"]["type"] for row in rows]
        self.assertIn("WorkTurnRecorded", types)
        self.assertIn("WorkToolRecorded", types)
        self.assertIn("WorkResultRecorded", types)
        self.assertIn("original candidate contents", canonical(rows))
        self.assertIn("original explanation before", canonical(rows))
        self.assertFalse((self.root / "example.txt").exists())
        self.assertEqual(profile.records("skill_progress"), [])
        self.assertEqual(capture.topics()[0]["technology"], "Flask")

    def test_capture_happens_before_the_final_model_response(self):
        original = work_harness.SelectedHarness.propose
        seen = []

        def observe(harness, root, request, **kwargs):
            if request["turns"]:
                types = {row["event"]["type"] for row in capture.traces()}
                seen.append(types)
                self.assertIn("WorkTurnRecorded", types)
                self.assertIn("WorkToolRecorded", types)
                self.assertNotIn("WorkResultRecorded", types)
            return original(harness, root, request, **kwargs)

        with mock.patch.object(work_harness.SelectedHarness, "propose", new=observe):
            result = self.work()
        self.assertTrue(result["ok"], result)
        self.assertTrue(seen)

    def test_malformed_learning_notes_do_not_destroy_work(self):
        result = self.work("Malformed")
        self.assertTrue(result["ok"], result)
        packet = guides.prepare(self.root, self.cfg, run_id=result["run_id"])
        self.assertTrue(packet["rejected_notes"])
        self.assertEqual(packet["annotations"], [])
        self.assertEqual(packet["coverage"]["unrecorded_reasoning_reconstructed"], False)

    def test_personal_index_failure_does_not_destroy_committed_work(self):
        with mock.patch.object(capture, "traces", side_effect=OSError("not used")):
            with mock.patch.object(capture.profile, "_put", side_effect=OSError("index unavailable")):
                result = self.work()
        self.assertTrue(result["ok"], result)
        state = runtime._state(self.root, self.cfg, result["run_id"])
        self.assertEqual(state["work_result"]["status"], "SUCCEEDED")

    def test_summary_full_and_original_are_distinct_read_only_views(self):
        self.work()
        created = self.guide()
        self.assertTrue(created["ok"], created)
        identity = created["guide"]["id"]
        revision = profile.revision()
        short = guides.read(identity)
        full = guides.read(identity, detail="full")
        source = guides.read(identity, detail="sources")
        self.assertIn("short entry point", short["summary"])
        self.assertNotIn("source_events", short)
        self.assertEqual(full["document"]["parts"][0]["basis"], "ADDITIONAL_EXPLANATION")
        self.assertIn("original candidate contents", canonical(source["source_events"]))
        self.assertEqual(source["source_sha256"], digest(source["source_events"]))
        self.assertEqual(profile.revision(), revision)
        self.assertEqual(profile.records("skill_progress"), [])

    def test_generation_failure_keeps_sources_and_successful_work(self):
        work = self.work("InvalidGuide")
        created = self.guide("InvalidGuide")
        self.assertFalse(created["ok"])
        self.assertEqual(created["guide"]["status"], "FAILED")
        original = guides.read(created["guide"]["id"], detail="sources")
        self.assertTrue(original["source_events"])
        self.assertEqual(runtime._state(self.root, self.cfg, work["run_id"])["work_result"]["status"], "SUCCEEDED")

    def test_skill_and_technology_use_the_same_original_trace(self):
        result = self.work("Swift")
        asset = {
            "id": "skill-acceptance", "kind": "skill_asset",
            "project_id": self.cfg["project"]["id"], "project_name": self.cfg["project"]["name"],
            "run_id": result["run_id"], "work_key": self.cfg["project"]["id"] + "/" + result["run_id"],
            "definition": {"title": "A compressed skill", "technology_tags": ["Swift"]},
            "created_at": profile.now(), "authority": "AI_PROPOSAL_NOT_EXECUTION_OR_MASTERY",
        }
        profile.put_record(asset)
        skill = guides.prepare(self.root, self.cfg, skill_id=asset["id"])
        technology = guides.prepare(self.root, self.cfg, technology="Swift")
        self.assertEqual(skill["trace"]["sha256"], technology["trace"]["sha256"])
        self.assertTrue(skill["annotations"])
        other = self.work("Rust")
        unrelated = guides.prepare(self.root, self.cfg, technology="Rust")
        self.assertNotEqual(unrelated["trace"]["sha256"], skill["trace"]["sha256"])
        self.assertEqual(other["work"]["status"], "SUCCEEDED")

    def test_revoked_profile_body_is_not_automatically_resent(self):
        profile.statement("PRIVATE-EXPERIENCE-MARKER", technology="Flask", share=True)
        self.work()
        self.assertIn("PRIVATE-EXPERIENCE-MARKER", canonical(capture.traces()))
        profile.configure({"share_with_ai": False})
        packet = guides.prepare(self.root, self.cfg, technology="Flask")
        self.assertNotIn("PRIVATE-EXPERIENCE-MARKER", canonical(packet))
        self.assertTrue(packet["profile_snapshot_history"])

    def test_unknown_source_or_invented_resource_is_rejected(self):
        self.work()
        created = self.guide()
        saved = profile.get_record(created["guide"]["id"])
        request = {
            "format": PERSONAL_REQUEST, "mode": "unpack",
            "trace": {"events": saved["source_events"]},
            "personal_context": {}, "web_search": {"results": []},
        }
        document = deepcopy(saved["document"])
        document["parts"][0]["source_event_ids"] = ["invented-source"]
        with self.assertRaises(LedgerError):
            validate_output(request, document)
        document = deepcopy(saved["document"])
        document["resources"] = [{"resource_id": "invented-book", "why": "No source", "suggested_focus": ""}]
        with self.assertRaises(LedgerError) as raised:
            validate_output(request, document)
        self.assertEqual(raised.exception.code, "LEARNING_RESOURCE_UNKNOWN")

    def test_web_search_is_explicit_and_recommendations_bind_to_results(self):
        self.work()
        from verantyx import learning_resources
        with self.assertRaises(LedgerError):
            self.guide(queries=["official documentation"])
        with mock.patch.object(learning_resources.BraveSearch, "search", return_value=[
                {"title": "Publisher source", "url": "https://example.org/book", "description": "A search snippet"}]) as search:
            result = self.guide(queries=["public book query"], approve_web=True, key="one-search")
            again = self.guide(queries=["public book query"], approve_web=True, key="one-search")
        self.assertTrue(result["ok"], result)
        search.assert_called_once_with("public book query")
        self.assertTrue(again["replayed"])
        full = result["guide"]
        self.assertEqual(full["document"]["resources"][0]["resource_id"], full["resources"]["results"][0]["id"])
        self.assertFalse(full["resources"]["project_text_sent"])

    def test_external_effects_are_unknown_even_with_a_launcher(self):
        value = deepcopy(sandbox.DEFAULT)
        value.update(mode="command", label="Passthrough fixture, NOT an isolation engine",
                     trusted_launcher=True, argv_prefix=[
                         sys.executable, "-c", "import os,sys;os.execv(sys.argv[1],sys.argv[1:])"])
        sandbox.configure(self.root, self.cfg, value=value, trusted=True)
        with self.assertRaises(LedgerError) as raised:
            work_harness.select(self.root, self.cfg)
        self.assertEqual(raised.exception.code, "SANDBOX_REQUIRES_EXTERNAL_WORK_HARNESS")
        work_harness.configure(self.root, self.cfg, mode="process", adapter=str(self.adapter), trust_process=True)
        result = self.work()
        self.assertTrue(result["ok"], result)
        self.assertIsNone(result["source_project_changed"])
        from verantyx.work_boundary import observation, message
        facts = observation(result["state"])
        self.assertEqual(facts["source_change_status"], "UNKNOWN_EXTERNAL_EFFECTS")
        self.assertFalse(facts["sandbox"]["isolation_verified"])
        self.assertNotIn("本体未変更", message(result["state"]))

    def test_missing_launcher_does_not_fall_back_to_native_process(self):
        value = deepcopy(sandbox.DEFAULT)
        value.update(mode="command", label="Missing fixture", trusted_launcher=True,
                     argv_prefix=[str(self.root / "missing-launcher")])
        sandbox.configure(self.root, self.cfg, value=value, trusted=True)
        work_harness.configure(self.root, self.cfg, mode="process", adapter=str(self.adapter), trust_process=True)
        with mock.patch.object(work_harness, "invoke_prepared") as native:
            with self.assertRaises(LedgerError) as raised:
                work_harness.select(self.root, self.cfg)
        self.assertEqual(raised.exception.code, "SANDBOX_LAUNCHER_UNAVAILABLE")
        native.assert_not_called()

    def test_cli_start_and_read_operations_do_not_invoke_a_model(self):
        self.work()
        created = self.guide()
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
        commands = [
            ["--help"],
            ["setup", "sandbox", "--show", "--json"],
            ["my-learning", "topics", "--json"],
            ["my-learning", "list", "--json"],
            ["my-learning", "show", "--id", created["guide"]["id"], "--detail", "sources", "--json"],
        ]
        for args in commands:
            with self.subTest(args=args):
                completed = subprocess.run(
                    [sys.executable, "-c", "from verantyx.cli import main;raise SystemExit(main())",
                     "--project", str(self.root), *args], env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_web_read_only_views_authentication_and_source_detail(self):
        self.work()
        created = self.guide()
        from verantyx.atlas_server import AtlasServer
        server = AtlasServer(0, "ja")
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            revision = profile.revision()
            with self.assertRaises(HTTPError) as unauthorized:
                urlopen(server.origin + "/api/guides", timeout=5)
            self.assertEqual(unauthorized.exception.code, 401)
            headers = {"Authorization": "Bearer " + server.token}
            for detail in ("summary", "full", "sources"):
                request = Request(server.origin + "/api/guide?id=" + created["guide"]["id"] + "&detail=" + detail,
                                  headers=headers)
                with urlopen(request, timeout=5) as response:
                    value = json.load(response)
                self.assertEqual(value["detail"], detail)
                self.assertTrue(value["read_only"])
            with self.assertRaises(HTTPError) as forbidden:
                urlopen(Request(server.origin + "/api/guide", data=b"{}", headers=headers, method="POST"), timeout=5)
            self.assertEqual(forbidden.exception.code, 405)
            self.assertEqual(profile.revision(), revision)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
