"""Real bounded subprocesses and isolated MCP calls, never production memory."""
from pathlib import Path
from unittest import mock
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

from verantyx import config
from verantyx.adapters.command_process import load_command
from verantyx.application import record_run
from verantyx.bridges import handoff_packet, memory_read, memory_save, propose
from verantyx.domain.codec import canonical, digest
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore

SOURCE = Path(__file__).resolve().parents[1] / "src"
VERA_SOURCE = Path(os.environ.get("VERANTYX_VERA_SOURCE", str(Path(__file__).resolve().parents[2] / "dependencies/call-me-vera")))
VERA_PYTHON = Path(os.environ.get("VERANTYX_VERA_PYTHON", str(VERA_SOURCE / ".venv/bin/python")))


class BridgeFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        (self.root / "allowed.txt").write_text("selected source\n")
        (self.root / "private.txt").write_text("NEVER_SEND_THIS_FILE")
        self.first = record_run(self.root, self.cfg, request="project task", run_id="bridge-run", observe_paths=["allowed.txt"])
        self.revision = self.first["state"]["revision"]

    def tearDown(self):
        self.temporary.cleanup()

    def adapter(self, body, *, filename="adapter", environment=None):
        path = self.root / (filename + ".py")
        path.write_text(body)
        specification = self.root / (filename + ".json")
        specification.write_text(json.dumps({"argv": [sys.executable, str(path)],
                                               "env": {"PYTHONPATH": str(SOURCE), **(environment or {})}}))
        return specification

    def proposer(self, prefix="", suffix="", filename="adapter"):
        return self.adapter("import json,sys\nfrom pathlib import Path\n" + prefix +
                            "value=json.load(sys.stdin)\ndocument=value['proposal_template']\n" + suffix +
                            "print(json.dumps(document))\n", filename=filename)

    def invoke(self, adapter, **kwargs):
        return propose(self.root, self.cfg, "bridge-run", adapter_path=adapter, key="generation",
                       expected_revision=self.revision, include_paths=["allowed.txt"], **kwargs)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(LedgerError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, caught.exception.details)

    def packet(self):
        path = self.root / "handoff.json"
        value = handoff_packet(self.root, self.cfg, run_ids=["bridge-run"], output=path)
        return path, value


class ProposalBridgeTests(BridgeFixture):
    def test_real_process_receives_only_selected_inputs_and_records_proposal_once(self):
        counter = self.root / "calls"
        captured = self.root / "captured.json"
        adapter = self.proposer(prefix=f"Path({str(counter)!r}).write_text('called')\n",
                                suffix=f"Path({str(captured)!r}).write_text(json.dumps(value))\n")
        first = self.invoke(adapter)
        self.assertEqual(first["state"]["proposal"]["task_id"], "bridge-run")
        self.assertFalse(first["state"]["can_execute_effects"])
        self.assertFalse(first["state"]["human_decisions"])
        self.assertFalse(first["state"]["effects"])
        payload = json.loads(captured.read_text())
        self.assertEqual(set(payload), {"format", "task", "proposal_schema", "proposal_template", "selected_files", "output_contract", "decision_context"})
        self.assertEqual(payload["decision_context"]["format"], "verantyx.decision-context.v1")
        self.assertEqual(payload["decision_context"]["items"], [])
        self.assertFalse(payload["decision_context"]["execution_authorized"])
        self.assertEqual([item["path"] for item in payload["selected_files"]], ["allowed.txt"])
        self.assertNotIn("NEVER_SEND_THIS_FILE", captured.read_text())
        self.assertNotIn(str(self.root), captured.read_text())
        counter.unlink()
        (self.root / "allowed.txt").write_text("changed after completed invocation")
        second = self.invoke(adapter)
        self.assertTrue(second["duplicate"])
        self.assertFalse(counter.exists())
        self.assertEqual(first["projection_hash"], second["projection_hash"])

    def test_shell_string_and_invalid_configuration_never_launch(self):
        target = self.root / "invalid.json"
        for value in ({"argv": "echo test"}, {"argv": ["/bin/sh", "-c", "echo unsafe"]},
                      {"argv": ["python3"]}, {"argv": [sys.executable], "untrusted": True}):
            target.write_text(json.dumps(value))
            self.assert_code("BRIDGE_CONFIG", load_command, target)

    def test_timeout_and_output_limits_are_enforced_while_process_is_running(self):
        adapter = self.adapter("import time\ntime.sleep(10)\n")
        self.assert_code("BRIDGE_TIMEOUT", self.invoke, adapter, timeout=0.1)
        for channel in ("stdout", "stderr"):
            with tempfile.TemporaryDirectory() as temporary:
                other = Path(temporary)
                cfg = config.defaults(other, "en")
                config.save(other, cfg, None)
                view = record_run(other, cfg, request="limits", run_id="test")
                adapter = self.adapter("import os,time\nos.write(" + ("1" if channel == "stdout" else "2") +
                                       ", b'x'*30000)\ntime.sleep(10)\n", filename=channel)
                self.assert_code("BRIDGE_OUTPUT_LIMIT", propose, other, cfg, "test", adapter_path=adapter,
                                 key="limit", expected_revision=view["recorded_revision"], max_output=4096, timeout=2)

    def test_invalid_json_context_and_self_approval_are_never_ledger_authority(self):
        cases = [("print('{\"a\":1,\"a\":2}')", "DOCUMENT_INVALID"),
                 ("import json,sys; p=json.load(sys.stdin)['proposal_template']; p['context_revision']=0; print(json.dumps(p))", "PROPOSAL_CONTEXT"),
                 ("import json,sys; p=json.load(sys.stdin)['proposal_template']; p['task_id']='another'; print(json.dumps(p))", "PROPOSAL_CONTEXT"),
                 ("import json,sys; p=json.load(sys.stdin)['proposal_template']; p['authorized']=True; print(json.dumps(p))", "PROPOSAL_INVALID"),
                 ("import json,sys; p=json.load(sys.stdin)['proposal_template']; p['actions']=[{'id':'own','tool_id':'authorize','arguments':{},'reason':'approve myself','source_refs':[]}]; print(json.dumps(p))", "PROPOSAL_INVALID")]
        for index, (body, expected) in enumerate(cases):
            adapter = self.adapter(body, filename="invalid-" + str(index))
            self.assert_code(expected, propose, self.root, self.cfg, "bridge-run", adapter_path=adapter,
                             key="invalid-" + str(index), expected_revision=self.revision)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(store.project_revision(), self.revision)

    def test_same_key_changed_executor_is_rejected(self):
        adapter = self.proposer()
        self.invoke(adapter)
        specification = json.loads(adapter.read_text())
        specification["env"]["DIFFERENT_EXECUTOR_INPUT"] = "changed"
        adapter.write_text(json.dumps(specification))
        self.assert_code("IDEMPOTENCY_CONFLICT", self.invoke, adapter)

    def test_selected_file_change_and_other_run_revision_change_reject_ingestion(self):
        adapter = self.proposer(suffix=f"Path({str(self.root / 'allowed.txt')!r}).write_text('concurrent edit')\n")
        self.assert_code("PROPOSAL_CONTEXT", self.invoke, adapter)
        (self.root / "allowed.txt").write_text("selected source\n")
        body = ("from verantyx import config\nfrom verantyx.application import record_run\n"
                f"root=Path({str(self.root)!r})\ncfg,_=config.load(root)\n"
                "record_run(root,cfg,request='concurrent context',run_id='another-run')\n")
        adapter = self.proposer(suffix=body, filename="other-run")
        self.assert_code("REVISION_CONFLICT", propose, self.root, self.cfg, "bridge-run", adapter_path=adapter,
                         key="other-run", expected_revision=self.revision)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            self.assertEqual(store.events("bridge-run")[-1]["revision"], self.revision)

    def test_unselected_symlink_and_unobserved_content_are_rejected(self):
        adapter = self.proposer()
        self.assert_code("PATH_SCOPE", propose, self.root, self.cfg, "bridge-run", adapter_path=adapter,
                         key="private", expected_revision=self.revision, include_paths=["private.txt"])
        (self.root / "allowed.txt").unlink()
        (self.root / "allowed.txt").symlink_to(self.root / "private.txt")
        self.assert_code("BRIDGE_INPUT_INVALID", self.invoke, adapter)

    def test_ledger_commit_then_process_crash_reuses_committed_receipt(self):
        counter = self.root / "counter"
        adapter = self.proposer(prefix=f"p=Path({str(counter)!r});p.write_text(p.read_text()+'x' if p.exists() else 'x')\n")
        script = """from pathlib import Path
import os,sys
from verantyx import config
from verantyx.bridges import propose
root=Path(sys.argv[1]);cfg,_=config.load(root)
def fault(stage):
 if stage=='after_record':os._exit(73)
propose(root,cfg,'bridge-run',adapter_path=sys.argv[2],key='generation',expected_revision=int(sys.argv[3]),include_paths=['allowed.txt'],fault=fault)
"""
        result = subprocess.run([sys.executable, "-c", script, str(self.root), str(adapter), str(self.revision)],
                                env={**os.environ, "PYTHONPATH": str(SOURCE)}, capture_output=True)
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual(counter.read_text(), "x")
        # Later project activity does not erase the already-committed receipt.
        record_run(self.root, self.cfg, request="later task", run_id="later")
        result = self.invoke(adapter)
        self.assertTrue(result["duplicate"])
        self.assertEqual(counter.read_text(), "x")

    def test_crash_boundaries_do_not_repeat_a_generation_process(self):
        counter = self.root / "counter"
        adapter = self.proposer(prefix=f"p=Path({str(counter)!r});p.write_text(p.read_text()+'x' if p.exists() else 'x')\n")
        script = """from pathlib import Path
import os,sys
from verantyx import config
from verantyx.bridges import propose
root=Path(sys.argv[1]);cfg,_=config.load(root)
def fault(stage):
 if stage==sys.argv[4]:os._exit(73)
propose(root,cfg,'bridge-run',adapter_path=sys.argv[2],key=sys.argv[3],expected_revision=int(sys.argv[5]),include_paths=['allowed.txt'],fault=fault)
"""
        for stage in ("after_started", "after_response"):
            result = subprocess.run([sys.executable, "-c", script, str(self.root), str(adapter), stage, stage, str(self.revision)],
                                    env={**os.environ, "PYTHONPATH": str(SOURCE)}, capture_output=True)
            self.assertEqual(result.returncode, 73, result.stderr)
            if stage == "after_started":
                self.assertFalse(counter.exists())
                self.assert_code("BRIDGE_OUTCOME_UNKNOWN", propose, self.root, self.cfg, "bridge-run", adapter_path=adapter,
                                 key=stage, expected_revision=self.revision, include_paths=["allowed.txt"])
            else:
                self.assertEqual(counter.read_text(), "x")
                recovered = propose(self.root, self.cfg, "bridge-run", adapter_path=adapter, key=stage,
                                    expected_revision=self.revision, include_paths=["allowed.txt"])
                self.assertTrue(recovered["ok"])
                self.assertEqual(counter.read_text(), "x")


class HandoffPacketTests(BridgeFixture):
    def test_real_decision_rule_and_learning_preserve_structure_but_exclude_original_prose(self):
        from verantyx.governance import control
        document = {"schema_version": 1, "task_id": "decision-run", "context_revision": 0, "response_locale": "ja",
                    "summary": "EXCLUDED_MODEL_SUMMARY", "claims": [], "actions": [], "unknowns": [],
                    "decision_points": [{"id": "scope", "kind": "VALUE_DECISION", "decision_type": "scoped-choice",
                                         "question": "EXCLUDED_QUESTION", "options": [
                                             {"id": "yes", "label": "EXCLUDED_LABEL_YES"}, {"id": "no", "label": "EXCLUDED_LABEL_NO"}]}]}
        path = self.root / "decision.json"
        path.write_text(json.dumps(document))
        record_run(self.root, self.cfg, request="EXCLUDED_REQUEST", run_id="decision-run", proposal_path=path,
                   context={"component": "test", "workload": "single", "risk": "LOW"})
        with EventStore(self.root, self.cfg["project"]["id"], create=True) as store:
            decision = control(store, self.cfg, "decide", "decision-run", point_id="scope", choice="yes", reason="EXCLUDED_HUMAN_REASON")
            control(store, self.cfg, "precedent-accept", decision["precedent_id"])
            control(store, self.cfg, "rule-draft", decision["precedent_id"])
        value = handoff_packet(self.root, self.cfg, run_ids=["decision-run"])["packet"]
        run = value["runs"][0]
        self.assertEqual(len(run["rules"]), 1)
        self.assertEqual(run["rules"][0]["choice"], "yes")
        self.assertEqual(run["rules"][0]["enforcement"], "OFF")
        self.assertEqual(len(run["learning"]), 1)
        self.assertEqual(run["learning"][0]["mastery_evidence"], "NONE")
        self.assertTrue(run["learning"][0]["source_refs"])
        self.assertNotIn("EXCLUDED_", canonical(value))

    def test_packet_has_project_rules_learning_unresolved_and_citations_without_raw_text(self):
        path, result = self.packet()
        value = result["packet"]
        self.assertEqual(value["authority"], "REFERENCE_ONLY")
        self.assertFalse(value["automatic_conversation_collection"])
        self.assertEqual(set(value["runs"][0]), {"run_id", "revision", "head_hash", "project", "rules", "learning", "unresolved", "source_refs"})
        self.assertTrue(value["runs"][0]["source_refs"])
        self.assertNotIn("project task", path.read_text())
        self.assertNotIn("selected source", path.read_text())
        self.assertNotIn("NEVER_SEND_THIS_FILE", path.read_text())
        self.assertEqual(result["file_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_packet_changed_or_forged_is_rejected_before_server_launch(self):
        path, result = self.packet()
        with mock.patch("verantyx.bridges.load_command", side_effect=AssertionError("server launched")):
            self.assert_code("MEMORY_PACKET_CHANGED", memory_save, self.root, self.cfg, packet_path=path,
                             expected_sha256="0" * 64, server_path="missing", name="test", key="save")
            packet = result["packet"]
            packet["runs"][0]["project"]["assessment"]["build"] = "COMPLETE"
            packet["packet_sha256"] = digest({key: value for key, value in packet.items() if key != "packet_sha256"})
            path.write_text(canonical(packet))
            self.assert_code("MEMORY_PACKET_INVALID", memory_save, self.root, self.cfg, packet_path=path,
                             expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), server_path="missing", name="test", key="save")

    def test_memory_name_is_always_required_before_a_process_starts(self):
        for value in ("", "../escape", "a/b", None):
            self.assert_code("MEMORY_NAME_REQUIRED", memory_save, self.root, self.cfg, packet_path="missing",
                             expected_sha256="0" * 64, server_path="missing", name=value, key="save")


@unittest.skipUnless(VERA_SOURCE.is_dir() and VERA_PYTHON.is_file(), "Set VERANTYX_VERA_SOURCE and VERANTYX_VERA_PYTHON for the real MCP fixture")
class VeraMCPIntegrationTests(BridgeFixture):
    def setUp(self):
        super().setUp()
        self.memory_home = self.root / "memory-home"
        self.memory_home.mkdir()
        self.server = self.root / "vera-server.json"
        self.server.write_text(json.dumps({"argv": [str(VERA_PYTHON), "-m", "vera.cli", "mcp", "--store", str(self.memory_home / "default.db")],
                                           "cwd": str(VERA_SOURCE), "env": {"HOME": str(self.memory_home), "PYTHONPATH": str(VERA_SOURCE)}}))
        self.memory_name = "verantyx-bridge-fixture"

    def test_real_named_mcp_save_read_search_and_local_retry(self):
        initial = memory_read(server_path=self.server, name=self.memory_name, operation="start", lang="ja")
        self.assertIn(self.memory_name, initial["result"])
        path, packet = self.packet()
        result = memory_save(self.root, self.cfg, packet_path=path, expected_sha256=packet["file_sha256"],
                             server_path=self.server, name=self.memory_name, key="save")
        self.assertEqual(result["receipt"]["memory"]["name"], self.memory_name)
        with mock.patch("verantyx.bridges.VeraMemory", side_effect=AssertionError("duplicate network write")):
            duplicate = memory_save(self.root, self.cfg, packet_path=path, expected_sha256=packet["file_sha256"],
                                    server_path=self.server, name=self.memory_name, key="save")
        self.assertTrue(duplicate["duplicate"])
        read = memory_read(server_path=self.server, name=self.memory_name, operation="read", limit=20, max_chars=20000)
        self.assertEqual(len(read["result"]["entries"]), 6)
        self.assertNotIn("project task", canonical(read))
        self.assertNotIn("selected source", canonical(read))
        search = memory_read(server_path=self.server, name=self.memory_name, operation="search", query=packet["packet"]["packet_sha256"])
        self.assertTrue(search["result"])
        lookup = memory_read(server_path=self.server, name=self.memory_name, operation="lookup", n=1)
        self.assertEqual(lookup["result"]["n"], 1)
        second = memory_read(server_path=self.server, name="another-fixture", operation="read")
        self.assertEqual(second["result"]["entries"], [])
        self.assertTrue((self.memory_home / ".vera/stores" / (self.memory_name + ".db")).is_file())

    def test_remote_commit_then_local_crash_never_automatically_resends(self):
        path, packet = self.packet()
        def crash(stage):
            if stage == "after_remote_save":
                raise RuntimeError("simulated process interruption")
        with self.assertRaises(RuntimeError):
            memory_save(self.root, self.cfg, packet_path=path, expected_sha256=packet["file_sha256"],
                        server_path=self.server, name=self.memory_name, key="uncertain-save", fault=crash)
        with mock.patch("verantyx.bridges.VeraMemory", side_effect=AssertionError("uncertain write retried")):
            self.assert_code("BRIDGE_OUTCOME_UNKNOWN", memory_save, self.root, self.cfg, packet_path=path,
                             expected_sha256=packet["file_sha256"], server_path=self.server, name=self.memory_name, key="uncertain-save")
        read = memory_read(server_path=self.server, name=self.memory_name, operation="read")
        self.assertEqual(len(read["result"]["entries"]), 6)


if __name__ == "__main__":
    unittest.main()
