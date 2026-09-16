"""Integration boundaries: original records, optional bridges and model handoff."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from unittest import mock

import test_learning_continuity as continuity
from verantyx import config, learning_capture, learning_guides, personal_profile as profile
from verantyx import notebook_bridge as bridge, learning_moments, model_roles, context_handoff
from verantyx import agent_runtime as runtime
from verantyx.errors import LedgerError


class NotebookConnections(continuity.LearningContinuity):
    # Reuse setup/helpers, not the parent's already-covered cases.
    def test_new_connections_do_not_replace_existing_connection_commands(self):
        from verantyx.cli import parse
        _, new = parse(["connections", "status"])
        self.assertEqual(new.command, "connections")
        _, existing = parse(["model-api-check", "--adapter", str(self.adapter)])
        self.assertEqual(existing.command, "model-api-check")

    def test_obsidian_first_exports_originals_and_graph_without_mastery(self):
        vault = self.base / "vault"
        bridge.connect(vault, confirmed=True, include_private=True, auto=True)
        work = self.work("Swift")
        view = bridge.graph()
        self.assertTrue(view["connected"])
        self.assertTrue(any(row["kind"] == "work" for row in view["nodes"]))
        self.assertTrue(view["obsidian_url"].startswith("obsidian://open?"))
        files = bridge.settings()["files"]
        traces = learning_capture.traces()
        entry = next(row for row in traces if row["event"]["type"] == "WorkTurnRecorded")
        text = (vault / files[entry["id"]]).read_text()
        self.assertIn("original explanation before", text)
        self.assertIn("[[Cleanroom/technologies/", text)
        self.assertEqual(profile.records("skill_progress"), [])
        self.assertEqual(work["work"]["status"], "SUCCEEDED")

    def test_owner_edits_in_vault_are_never_overwritten(self):
        self.work()
        vault = self.base / "vault"
        bridge.connect(vault, confirmed=True, include_private=True)
        path = next(iter(bridge.settings()["files"].values()))
        target = vault / path
        target.write_text("Owner-written addition")
        with self.assertRaises(LedgerError):
            bridge.sync()
        self.assertEqual(target.read_text(), "Owner-written addition")

    def test_imported_skill_preserves_source_and_does_not_import_mastery(self):
        text = "---\nname: from-another-agent\nhuman_mastery: COMPLETE\n---\n# A procedure\nDo not run this as a hook."
        imported = bridge.import_text(text, origin="Other agent", title="Imported procedure",
                                      technologies=["Python"], confirmed=True)
        asset = profile.get_record(imported["id"])
        self.assertEqual(asset["source_text"], text)
        self.assertEqual(imported["human_state"], "NO_RECORD")
        self.assertFalse(imported["scripts_executed"])
        self.assertEqual(profile.records("skill_progress"), [])
        packet = learning_guides.prepare(self.root, self.cfg, skill_id=asset["id"])
        self.assertIn(text, [row["payload"].get("source_text") for row in packet["trace"]["events"]])
        self.assertFalse(packet["coverage"]["unrecorded_reasoning_reconstructed"])

    def test_understanding_is_an_explicit_bound_statement_not_an_inference(self):
        self.work()
        moment = learning_moments.entries()[0]
        self.assertEqual(profile.records("statement"), [])
        statement = learning_moments.record_understanding(
            moment["id"], "STILL_EXPLORING", "I want to revisit this boundary next time.", share=False)
        self.assertEqual(statement["kind"], "statement")
        self.assertEqual(statement["source"]["owner_state"], "STILL_EXPLORING")
        self.assertEqual(profile.records("skill_progress"), [])
        self.assertNotIn(statement["id"], json.dumps(profile.shared_context()))

    def test_handoff_survives_a_parent_model_change(self):
        first = self.work("First model")
        model_roles.register(self.root, self.cfg, "next", str(self.adapter), confirmed=True)
        model_roles.choose(self.root, self.cfg, "parent", "next", confirmed=True)
        seen = []
        from verantyx.work_harness import SelectedHarness
        original = SelectedHarness.propose
        def observe(harness, root, request, **kwargs):
            seen.append(deepcopy(request))
            return original(harness, root, request, **kwargs)
        with mock.patch.object(SelectedHarness, "propose", new=observe):
            second = self.work("Continue", continue_from=first["run_id"])
        self.assertTrue(second["ok"], second)
        handoff = seen[0]["project_context"]["model_handoff"]
        self.assertEqual(handoff["run_id"], first["run_id"])
        self.assertTrue(handoff["archive_available"])
        self.assertTrue(handoff["events"])
        event = handoff["events"][0]
        body = context_handoff.read(self.root, self.cfg, first["run_id"], event["source_ref"],
                                    allowed_runs={first["run_id"]})
        self.assertEqual(json.loads(body), event)

    def test_compaction_omits_input_not_original_records(self):
        work = self.work()
        before = len(learning_capture.traces())
        request = {"turns": [{"index": i, "source_ref": str(i), "text": "x" * 5000} for i in range(30)],
                   "tool_receipts": [], "project_context": {}, "request": "Keep the purpose"}
        packed, metadata = context_handoff.compact(request, budget=30000)
        self.assertTrue(metadata["compacted"])
        self.assertLess(len(packed["turns"]), len(request["turns"]))
        self.assertEqual(len(request["turns"]), 30)
        self.assertEqual(len(learning_capture.traces()), before)
        self.assertEqual(runtime._state(self.root, self.cfg, work["run_id"])["work_result"]["status"], "SUCCEEDED")

    def test_natural_language_switch_proposal_needs_owner_confirmation(self):
        model_roles.register(self.root, self.cfg, "child", str(self.adapter), confirmed=True)
        proposed = model_roles.request_switch(self.root, self.cfg, "child", "child")
        self.assertEqual(proposed["status"], "PENDING_OWNER")
        self.assertIsNone(model_roles.selected(self.root, "child"))
        with model_roles.owner_confirmation(lambda proposal: True):
            selected = model_roles.request_switch(self.root, self.cfg, "child", "child")
        self.assertEqual(selected["status"], "OWNER_SELECTED")
        self.assertEqual(model_roles.selected(self.root, "child"), str(self.adapter))
        advice = model_roles.consult(self.root, self.cfg, "Advice", source_request={"run_id": "advice-fixture"},
                                     key="child-advice", timeout=10)
        self.assertEqual(advice["authority"], "CHILD_ADVICE_NOT_EXECUTION")
        self.assertTrue(advice["proposed_tools_not_executed"])
        self.assertFalse((self.root / "example.txt").exists())

    def test_owner_projection_contains_implementation_notes_before_reflection(self):
        work = self.work()
        from verantyx.cleanroom_owner import catalogue, render_owner
        from verantyx.agent_projection import owner_projection
        state = runtime._state(self.root, self.cfg, work["run_id"])
        view = {"state": state, "run_id": work["run_id"], "revision": state["revision"],
                "ownership_projection": owner_projection(state)}
        items = catalogue(view)
        self.assertTrue(any(row["kind"] == "learning" for row in items))
        self.assertIn("DURING WORK", render_owner(view, items))

    def test_configured_english_web_and_graph_api(self):
        from verantyx.atlas_server import AtlasServer
        import threading
        from urllib.request import Request, urlopen
        current, expected = config.load(self.root)
        current["ui"]["locale"] = "en"
        config.save(self.root, current, expected)
        server = AtlasServer(0, "en", self.root)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        try:
            headers = {"Authorization": "Bearer " + server.token}
            with urlopen(Request(server.origin + "/api/atlas", headers=headers), timeout=5) as response:
                data = json.load(response)
            self.assertEqual(data["locale"], "en")
            self.assertIn("connections", data)
            with urlopen(server.origin + "/", timeout=5) as response:
                html = response.read().decode()
            self.assertIn('lang="en"', html)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_candidate_mount_placeholders_distinguish_store_from_workspace(self):
        from verantyx import sandbox_backends as sandbox
        value = deepcopy(sandbox.DEFAULT)
        value.update(mode="command", trusted_launcher=True,
                     argv_prefix=[sys.executable, "{candidate_root}", "{candidate_store}", "{workspace_root}"])
        command = {"argv": [sys.executable, "-c", "pass"], "identity": "fixture", "env": {}, "cwd": None}
        prepared, descriptor = sandbox.CommandSandboxBackend(value, "fixture").prepare(command, self.root)
        self.assertEqual(prepared["argv"][1], str(self.root / ".verantyx/workspaces"))
        self.assertEqual(prepared["argv"][2], str(self.root / ".verantyx/work-candidates"))
        self.assertEqual(prepared["argv"][3], str(self.root / ".verantyx/workspaces"))
        self.assertFalse(descriptor["isolation_verified"])

    def test_real_mcp_stdio_capture_and_passive_skill_import(self):
        async def exercise():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
            parameters = StdioServerParameters(command=sys.executable,
                args=["-c", "from verantyx.cli import main;raise SystemExit(main())",
                      "--project", str(self.root), "mcp", "--allow-personal", "--allow-import"], env=env)
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    names = {tool.name for tool in tools.tools}
                    self.assertIn("record_work_note", names)
                    self.assertNotIn("mark_mastered", names)
                    recorded = await client.call_tool("record_work_note", {
                        "session": "external-session", "key": "step-1", "model": "Other model",
                        "title": "Preserve this intermediate choice", "text": "Details before final summarization.",
                        "technologies": ["Swift"]})
                    self.assertFalse(recorded.isError)
                    listed = await client.call_tool("list_learning_moments", {"limit": 10})
                    self.assertFalse(listed.isError)
                    self.assertIn("intermediate choice", str(listed))
                    imported = await client.call_tool("import_skill", {
                        "text": "# Procedure\nAn imported draft", "origin": "Other agent",
                        "title": "Portable skill", "technologies": ["Python"]})
                    self.assertFalse(imported.isError)
        asyncio.run(asyncio.wait_for(exercise(), timeout=25))
        self.assertEqual(profile.records("skill_progress"), [])


    def test_switched_native_adapter_never_claims_source_unchanged(self):
        from verantyx.work_boundary import observation
        state = {"work_session": {"work_model": {"provider": "openai"},
                    "context": {"work_harness": {"kind": "builtin", "authority": "HOST_TOOLS_ONLY"}}},
                 "work_turns": [{"model": {"provider": "explicit_adapter"}}]}
        self.assertIsNone(observation(state)["source_project_changed"])
        state["work_turns"] = []
        state["work_tools"] = [{"request": {"tool": "consult_child"}}]
        self.assertIsNone(observation(state)["source_project_changed"])

    def test_external_moment_can_be_unpacked_without_local_run_or_technology_guess(self):
        from verantyx.notebook_mcp import record_external_note
        record_external_note("other-session", "before-change", "Other model",
                             "An intermediate decision", "Original rationale supplied as an explanation.", [])
        moment = learning_moments.entries()[0]
        packet = learning_guides.prepare(self.root, self.cfg, moment_id=moment["id"])
        self.assertEqual(packet["work_keys"], ["external/other-session"])
        self.assertIn("Original rationale", packet["trace"]["events"][0]["payload"]["text"])
        self.assertEqual(packet["target"]["technology"], "")


# The original fourteen cases run separately in test_learning_continuity.
for _name in list(continuity.LearningContinuity.__dict__):
    if _name.startswith("test_") and _name not in NotebookConnections.__dict__:
        setattr(NotebookConnections, _name, None)
