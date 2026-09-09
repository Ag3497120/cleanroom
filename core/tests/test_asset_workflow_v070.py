"""Artificial generators exercise real compilation, verifier and replay paths."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock
import base64
import json
import sys
import tempfile
import unittest

from verantyx import config
from verantyx.application import record_run
from verantyx.asset_workflow import run_asset_workflow
from verantyx.assets import project_assets
from verantyx.domain.asset_workflow import compile_document, output_schema, validate_project_bindings
from verantyx.domain.codec import digest
from verantyx.domain.events import make_event
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.storage.sqlite import EventStore
from verantyx.verification import plan_verification, run_verification


MODEL = r'''
import base64,json,os,pathlib,sys
r=json.load(sys.stdin); c=r['context']; mode=os.environ['MODE']
counter=pathlib.Path(os.environ['COUNTER'])
n=int(counter.read_text())+1 if counter.exists() else 1
counter.write_text(str(n))
pathlib.Path(os.environ['INPUT']).write_text(json.dumps(r))
s={'id':'property','mode':'COMPILE','claim_id':c['claims'][0]['id'],
   'target_path':c['selected_files'][0]['path'],'asset_id':None,
   'property':'/answer is integer 42','method':'TEST',
   'checks':[{'id':'answer','kind':'json.equals','pointer':'/answer','expected':42}],
   'negative_controls':[],'expectation_basis':'The synthetic request requires answer=42.',
   'source_refs':[c['request_ref']]}
if mode=='reuse' or mode=='alter_reuse':
    a=c['available_methods'][0]
    s.update(mode='REUSE',asset_id=a['id'],property=None,method=None,checks=[],negative_controls=[],source_refs=[a['source_ref']])
    if mode=='alter_reuse':s['checks']=[{'id':'weaker','kind':'json.equals','pointer':'/answer','expected':0}]
if mode=='negative':
    s.update(method='NEGATIVE_CONTROL',negative_controls=[{'id':'wrong','input_base64':base64.b64encode(b'{"answer":41}').decode()}])
if mode=='unsupported' or (mode=='repair' and n==1): s['checks'][0]['kind']='python.eval'
if mode=='foreign':s['source_refs']=['foreign:event']
if mode=='unselected':s['target_path']='private.json'
if mode=='weak_source':s['source_refs']=[c['request_ref']]
steps=[s]
if mode=='multiple':
    other=dict(s);other.update(id='truth',property='/ok true',checks=[{'id':'ok','kind':'json.equals','pointer':'/ok','expected':True}]);steps.append(other)
if mode=='none':steps=[]
if mode=='invalidjson': print('not json');sys.exit(0)
print(json.dumps({'format':'verantyx.asset-workflow-plan.v1','context_sha256':r['context_sha256'],'steps':steps,'unresolved':[]}))
'''


class AssetWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.cfg = config.defaults(self.root, "ja")
        config.save(self.root, self.cfg, None)
        self.time = datetime(2026, 9, 7, tzinfo=timezone.utc)
        self.clock = lambda: self.time
        (self.root / "report.json").write_text('{"answer":42,"ok":true}')
        self.request("first")
        self.script = self.root / "model.py"
        self.script.write_text(MODEL)
        self.counter = self.root / "calls"
        self.adapter = self.root / "adapter.json"
        self.adapter_mode("compile")

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, name, paths=("report.json",)):
        first = record_run(self.root, self.cfg, request="Synthetic: answer must equal integer 42 and ok must be true.",
                           run_id=name, observe_paths=paths, clock=self.clock)
        proposal = {"schema_version": 1, "task_id": name, "context_revision": first["state"]["revision"],
                    "response_locale": "ja", "summary": "Synthetic output to check.", "claims": [{"id": "answer",
                    "statement": "Output answer equals 42.", "source_refs": [first["state"]["request_ref"]]}],
                    "actions": [], "unknowns": []}
        path = self.root / (name + "-proposal.json")
        path.write_text(json.dumps(proposal))
        return record_run(self.root, self.cfg, run_id=name, proposal_path=path, resume=True, clock=self.clock)

    def adapter_mode(self, mode):
        self.adapter.write_text(json.dumps({"argv": [sys.executable, str(self.script)], "env": {
            "MODE": mode, "COUNTER": str(self.counter), "INPUT": str(self.root / "model-input.json")}}))

    def call(self, name="first", key="workflow", **kwargs):
        return run_asset_workflow(self.root, self.cfg, name, adapter_path=self.adapter, key=key,
                                  include_paths=("report.json",), clock=self.clock, **kwargs)

    def events(self, run_id=None):
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            return store.events(run_id)

    def test_compiles_and_executes_real_finite_contract_without_authority(self):
        result = self.call()
        self.assertEqual(result["workflow"]["status"], "COMPLETED")
        self.assertEqual(result["workflow"]["results"][0]["closure"], "BOUNDED")
        self.assertEqual(result["workflow"]["results"][0]["expectation_origin"], "MODEL_PROPOSED")
        self.assertEqual(result["workflow"]["results"][0]["independence"], "NOT_ESTABLISHED")
        self.assertFalse(result["authority_granted"])
        self.assertFalse(result["state"]["can_execute_effects"])
        self.assertEqual(result["state"]["effects"], {})
        self.assertEqual(result["state"]["human_decisions"], {})
        self.assertEqual(result["recorded_revision"], result["state"]["revision"])
        assets = project_assets(result["state"])
        self.assertEqual(len(assets["verification_methods"]), 1)
        plan = result["workflow"]["plan"]["steps"][0]["spec"]
        self.assertIn("MODEL_PROPOSED", plan["oracle"]["description"])
        sent = json.loads((self.root / "model-input.json").read_text())
        self.assertNotIn("config", sent)
        self.assertEqual(sent["format"], "verantyx.asset-workflow-request.v1")
        self.assertEqual(sent["planning_contract_version"], 4)
        self.assertEqual(sent["output_schema"], output_schema(4, sent["context"], source_value_sampling=True))

    def test_failure_is_preserved_not_replanned_to_lower_expectation(self):
        (self.root / "report.json").write_text('{"answer":0,"ok":true}')
        record_run(self.root, self.cfg, run_id="first", resume=True, clock=self.clock)
        result = self.call()
        self.assertEqual(result["workflow"]["status"], "REFUTED")
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(self.counter.read_text(), "1")
        self.assertEqual(result["workflow"]["plan"]["steps"][0]["spec"]["checks"][0]["expected"], 42)
        self.assertEqual(len(project_assets(result["state"])["failure_cases"]), 1)

    def test_reuse_in_new_task_preserves_checks_and_negative_controls(self):
        self.adapter_mode("negative")
        first = self.call()
        old = first["workflow"]["plan"]["steps"][0]["spec"]
        (self.root / "report.json").write_text('{"answer":42,"ok":false}')
        self.request("second")
        self.adapter_mode("reuse")
        second = self.call("second", key="second")
        new = second["workflow"]["plan"]["steps"][0]["spec"]
        for key in ("checks", "negative_controls", "property", "method", "provenance"):
            self.assertEqual(old[key], new[key])
        self.assertNotEqual(old["oracle"]["source_refs"], new["oracle"]["source_refs"])
        self.assertEqual(second["workflow"]["status"], "COMPLETED")
        self.assertEqual(second["workflow"]["results"][0]["expectation_origin"], "RECORDED_CONTRACT_NEW_BINDING")
        self.assertEqual(self.counter.read_text(), "2")

    def test_malformed_plan_repairs_once_before_any_verifier(self):
        self.adapter_mode("repair")
        result = self.call()
        self.assertEqual(result["workflow"]["status"], "COMPLETED")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(len(result["workflow"]["plan"]["rejected"]), 1)
        self.assertEqual(len(result["state"]["verifications"]), 1)

    def test_unsupported_or_unknown_sources_never_execute(self):
        for index, mode in enumerate(("unsupported", "foreign", "unselected", "invalidjson")):
            self.adapter_mode(mode)
            result = self.call(key="bad-" + str(index))
            self.assertEqual(result["workflow"]["status"], "NO_PLAN")
            self.assertEqual(result["model_calls"], 2)
            self.assertEqual(len(result["workflow"]["plan"]["rejected"]), 2)
            self.assertEqual(result["state"].get("verifications", {}), {})

    def test_malformed_structural_values_are_controlled_rejections(self):
        result = self.call(execute=False)
        context = result["workflow"]["plan"]["context"]
        original = result["workflow"]["plan"]["document"]
        for field in ("id", "claim_id", "target_path", "asset_id", "method", "checks", "negative_controls", "source_refs"):
            for bad in (None, {}, ["wrong"], 42):
                value = deepcopy(original)
                value["steps"][0][field] = bad
                if field == "asset_id" and bad is None:
                    continue
                try:
                    compile_document(context, value, 4)
                except LedgerError:
                    pass
                else:
                    self.fail("malformed field accepted: " + field)

    def test_model_cannot_modify_reused_expectation(self):
        self.call()
        self.adapter_mode("alter_reuse")
        result = self.call(key="altered")
        self.assertEqual(result["workflow"]["status"], "NO_PLAN")
        self.assertEqual(result["workflow"]["plan"]["rejected"][0]["reason"], "FROZEN_CONTRACT_CHANGED")
        self.assertEqual(len(result["state"]["verifications"]), 1)

    def test_preview_records_compiled_contract_without_running_it(self):
        result = self.call(execute=False)
        self.assertEqual(result["workflow"]["status"], "PLANNED")
        self.assertEqual(result["state"].get("verifications", {}), {})
        with self.assertRaisesRegex(LedgerError, "IDEMPOTENCY_CONFLICT"):
            self.call(execute=True)

    def test_multiple_checks_are_frozen_before_observation_refresh(self):
        self.adapter_mode("multiple")
        result = self.call()
        self.assertEqual(result["workflow"]["status"], "COMPLETED")
        self.assertEqual(len(result["workflow"]["results"]), 2)
        kinds = [e["type"] for e in self.events("first")]
        self.assertLess(max(i for i,k in enumerate(kinds) if k == "VerificationPlanned"), kinds.index("VerificationStarted"))

    def test_total_predicate_limit_applies_to_compiled_and_reused_contracts(self):
        self.adapter_mode("multiple")
        result = self.call(max_checks=1)
        self.assertEqual(result["workflow"]["status"], "NO_PLAN")
        self.assertEqual(result["state"].get("verifications", {}), {})

    def test_completed_idempotency_returns_same_receipts_without_model(self):
        first = self.call()
        (self.root / "report.json").write_text('{"answer":99}')
        second = self.call()
        self.assertEqual(first["recorded_revision"], second["recorded_revision"])
        self.assertEqual(first["workflow"], second["workflow"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(self.counter.read_text(), "1")

    def test_uncertain_model_invocation_never_calls_again(self):
        def interrupt(stage):
            if stage == "after_invocation_started":
                raise RuntimeError("crash")
        with self.assertRaisesRegex(RuntimeError, "crash"):
            self.call(fault=interrupt)
        with self.assertRaisesRegex(LedgerError, "BRIDGE_OUTCOME_UNKNOWN"):
            self.call()
        self.assertFalse(self.counter.exists())

    def test_resume_saved_model_response_plan_and_check_receipts(self):
        for index, stage_name in enumerate(("after_model_response", "after_plan", "after_check")):
            name = "resume-" + str(index)
            self.request(name)
            def interrupt(stage):
                if stage == stage_name:
                    raise RuntimeError("crash")
            with self.assertRaisesRegex(RuntimeError, "crash"):
                self.call(name, key=name, fault=interrupt)
            result = self.call(name, key=name)
            self.assertEqual(result["workflow"]["status"], "COMPLETED")
        self.assertEqual(self.counter.read_text(), "3")

    def test_file_changed_after_saved_context_stops_before_model(self):
        def change(stage):
            if stage == "after_context_saved":
                (self.root / "report.json").write_text('{"answer":99}')
        with self.assertRaises(LedgerError):
            self.call(fault=change)
        self.assertFalse(self.counter.exists())

    def test_launcher_script_changed_after_context_stops_before_model(self):
        def change(stage):
            if stage == "after_context_saved":
                self.script.write_text(MODEL + "\n# changed\n")
        with self.assertRaisesRegex(LedgerError, "JOB_ADAPTER_CHANGED"):
            self.call(fault=change)
        self.assertFalse(self.counter.exists())

    def test_revision_change_after_model_response_never_reinterprets(self):
        def change(stage):
            if stage == "after_model_response":
                record_run(self.root, self.cfg, run_id="first", resume=True, clock=self.clock)
        with self.assertRaisesRegex(LedgerError, "REVISION_CONFLICT"):
            self.call(fault=change)
        with self.assertRaisesRegex(LedgerError, "REVISION_CONFLICT"):
            self.call()
        self.assertEqual(self.counter.read_text(), "1")

    def test_selected_requirements_are_pinned_even_if_model_does_not_cite_them(self):
        (self.root / "requirements.txt").write_text("answer=42")
        record_run(self.root, self.cfg, run_id="first", resume=True, observe_paths=["requirements.txt"], clock=self.clock)
        def change(stage):
            if stage == "after_plan":
                (self.root / "requirements.txt").write_text("answer=99")
        result = run_asset_workflow(self.root, self.cfg, "first", adapter_path=self.adapter, key="files",
                                   include_paths=("report.json", "requirements.txt"), clock=self.clock, fault=change)
        self.assertEqual(result["workflow"]["status"], "INVALIDATED")
        self.assertEqual(result["workflow"]["results"][0]["reason"], "ORACLE_CHANGED")

    def test_replay_rejects_changed_sources_specs_and_results(self):
        self.call()
        self.adapter_mode("reuse")
        self.call(key="reuse")
        events = self.events()
        planned = next(e for e in reversed(events) if e["type"] == "AssetWorkflowPlanned")
        forged = deepcopy(planned)
        method = forged["payload"]["context"]["available_methods"][0]
        method["spec"]["checks"][0]["expected"] = 99
        method["contract_hash"] = digest(method["spec"])
        with self.assertRaisesRegex(LedgerError, "ASSET_WORKFLOW_INVALID"):
            validate_project_bindings([forged if e is planned else e for e in events])
        for mutation in ("claim", "file", "spec", "result"):
            stream = self.events("first")
            forged_stream = []
            changed = False
            for e in stream:
                p = deepcopy(e["payload"])
                if not changed and e["type"] == "AssetWorkflowPlanned" and mutation != "result":
                    if mutation == "claim":p["context"]["claims"][0]["statement"] = "changed"
                    elif mutation == "file":p["context"]["selected_files"][0]["text"] = "changed"
                    elif mutation == "spec":p["steps"][0]["spec"]["checks"][0]["expected"] = 99
                    changed = True
                elif not changed and e["type"] == "AssetWorkflowFinished" and mutation == "result":
                    p["status"] = "REFUTED"; changed = True
                try:
                    rebuilt = make_event(e["project_id"], e["stream_id"], e["revision"], e["command_id"], e["recorded_at"],
                                         e["type"], p, e["event_id"], forged_stream[-1] if forged_stream else None)
                    forged_stream.append(rebuilt)
                except LedgerError:
                    break
            else:
                with self.assertRaises(LedgerError): replay(forged_stream)

    def test_verifier_revision_guard_allows_own_interruption_only(self):
        preview = self.call(execute=False)
        spec = preview["workflow"]["plan"]["steps"][0]["spec"]
        plan = plan_verification(self.root, self.cfg, "first", spec, "direct-plan", clock=self.clock)
        revision = plan["state"]["revision"]
        def crash(stage):
            if stage == "after_start":raise RuntimeError("crash")
        with self.assertRaises(RuntimeError):
            run_verification(self.root, self.cfg, "first", plan["verification_id"], "direct-run",
                             expected_revision=revision, clock=self.clock, fault=crash)
        result = run_verification(self.root, self.cfg, "first", plan["verification_id"], "direct-run",
                                  expected_revision=revision, clock=self.clock)
        self.assertEqual(result["verification"]["status"], "OUTCOME_UNKNOWN")

    def test_no_claims_or_selected_files_returns_explicit_gap_without_model(self):
        record_run(self.root, self.cfg, request="Synthetic uncompiled task", run_id="empty", clock=self.clock)
        result = run_asset_workflow(self.root, self.cfg, "empty", adapter_path=self.adapter, key="empty", clock=self.clock)
        self.assertEqual(result["workflow"]["status"], "NO_PLAN")
        self.assertEqual(result["model_calls"], 0)
        self.assertFalse(self.counter.exists())

    def test_expired_selected_observation_never_becomes_a_fresh_check(self):
        self.time += timedelta(minutes=6)
        with self.assertRaises(LedgerError):self.call()
        self.assertFalse(any(e["type"] == "VerificationStarted" for e in self.events("first")))


if __name__ == "__main__":
    unittest.main()
