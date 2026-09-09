"""Original-source retention, independent editor boundaries and actual Cross VM.

Models below are deterministic protocol fixtures, not semantic accuracy evals.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import test_responses_v06 as response_fixtures
from verantyx.application import record_run
from verantyx.responses import ask
from verantyx.shared_context import record_context, validate_plan, validate_packet
from verantyx.coordination import coordinate, candidate_proposal, stage_candidate, comparison_inputs, validate_editor
from verantyx.adapters.cross_context import compare, validate_result
from verantyx.assets import project_catalog
from verantyx.domain.codec import digest
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.storage.sqlite import EventStore


class SharedContextTests(unittest.TestCase):
    def setUp(self):
        self.fixture = response_fixtures.ResponseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root, self.cfg = self.fixture.root, self.fixture.cfg

    def error(self, code, fn, *args, **kwargs):
        with self.assertRaises(LedgerError) as error:
            fn(*args, **kwargs)
        self.assertEqual(error.exception.code, code)

    def adapters(self, editor_mutation="", planner_mutation=""):
        common = """import json,sys
from pathlib import Path
v=json.load(sys.stdin)
with Path(CALLS).open('a') as f: f.write(json.dumps(v)+'\\n')
if v['format']=='verantyx.proposal-request.v1':
 d=v['proposal_template']; d['summary']='A proposal, not an execution.'
elif v['format']=='verantyx.response-request.v1':
 d=v['response_template']; d['answer']='The separate editor returned a candidate; tests have not run.'
 d['learning_candidates']=[]; d['reusable_candidates']=[]
elif v['format']=='verantyx.handoff-plan-request.v1':
 d=v['response_template']; d['interpretations']=[]
 for i,s in enumerate(v['shared_context']['sources']):
  d['interpretations'].append(dict(id='now-'+str(i),source_id=s['id'],quote=s['text'],meaning='Connect first.',disposition='NOW',strength='MUST',alternatives=[]))
 s=v['shared_context']['sources'][0]
 d['interpretations'].append(dict(id='later',source_id=s['id'],quote=s['text'],meaning='Independence remains deferred, not cancelled.',disposition='DEFERRED',strength='MUST',alternatives=[]))
 d['relations']=[dict(kind='PRIORITY_OVER',**{'from':'now-0','to':'later'})]
 d['cases']=[dict(id='sequence',situation='Should independence be cancelled after connecting?',choices=[dict(id='retain',text='Keep it as later work.'),dict(id='cancel',text='Remove it entirely.')],expected='retain',interpretation_ids=['now-0','later'])]
 PLAN_MUTATION
else:
 d=v['response_template']; p=v['interpretation_proposal']
 d['acknowledgements']=[dict(id=n['id'],disposition=n['disposition'],strength=n['strength'],interpretation=n['meaning'],alternatives=n['alternatives']) for n in p['interpretations']]
 d['relations']=p['relations']; d['case_choices']=[dict(id='sequence',choice='retain',reason='Later does not mean cancelled.')]
 d['files']={'calc.py':'def answer():\\n    return 2\\n'}
 d['tests']=['test_calc.py']; d['notes']='Proposed calc.py correction, not yet executed.'
 EDIT_MUTATION
print(json.dumps(d))
"""
        result = []
        for role, mutation, plan_change in (("vera", "pass", planner_mutation or "pass"), ("editor", editor_mutation or "pass", "pass")):
            path = self.root / (role + '.py')
            path.write_text(common.replace('CALLS', repr(str(self.fixture.calls))).replace('PLAN_MUTATION', plan_change).replace('EDIT_MUTATION', mutation))
            adapter = self.root / (role + '.json')
            adapter.write_text(json.dumps({'argv': [sys.executable, str(path)]}))
            result.append(adapter)
        self.root.joinpath('calc.py').write_text('def answer():\n    return 1\n')
        self.root.joinpath('test_calc.py').write_text('import unittest\nfrom calc import answer\nclass Check(unittest.TestCase):\n    def test_answer(self):\n        self.assertEqual(answer(),2)\n')
        return result

    def workflow(self, mutation="", planner_mutation="", **kwargs):
        vera, editor = self.adapters(mutation, planner_mutation)
        return ask(self.root, self.cfg, request='Connect first; independence is deferred.', adapter_path=vera, editor_adapter=editor,
                   include_paths=['calc.py', 'test_calc.py'], key='work', run_id='work', **kwargs)

    def test_distinct_models_receive_identical_original_version_and_candidate_is_inert(self):
        result = self.workflow()
        calls = self.fixture.invocations()
        self.assertEqual(len(calls), 4)
        self.assertEqual([c['format'] for c in calls], ['verantyx.proposal-request.v1', 'verantyx.handoff-plan-request.v1',
                         'verantyx.editor-request.v1', 'verantyx.response-request.v1'])
        packets = [c['shared_context'] for c in calls]
        self.assertTrue(all(p == packets[0] for p in packets))
        self.assertNotIn('expected', calls[2]['interpretation_proposal']['cases'][0])
        state = result['state']
        self.assertEqual(state['editor_attempt']['validation']['mode'], 'CROSS_VM')
        self.assertEqual(state['editor_attempt']['validation']['status'], 'MATCHED')
        self.assertEqual(state['proposal']['actions'][0]['tool_id'], 'writer.apply')
        self.assertEqual(state['effects'], {})
        self.assertEqual(state['human_decisions'], {})
        self.assertEqual(self.root.joinpath('calc.py').read_text(), 'def answer():\n    return 1\n')

    def test_deferred_changed_to_forbidden_is_retained_and_repaired(self):
        result = self.workflow("if not v['repair_feedback']: d['acknowledgements'][-1]['disposition']='FORBIDDEN'")
        attempts = result['state']['editor_attempts']
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]['validation']['mismatch_ids'], ['later:disposition'])
        self.assertEqual(attempts[1]['validation']['status'], 'MATCHED')
        self.assertEqual(attempts[0]['context_sha256'], attempts[1]['context_sha256'])
        with EventStore(self.root, self.cfg['project']['id']) as store:
            catalog = project_catalog(store, result['state'], 'ja')
        failures = [f for f in catalog['failure_cases'] if f['family']=='HANDOFF']
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]['expectation_origin'], 'MODEL_INTERPRETATION')

    def test_endless_disagreement_stops_at_explicit_repair_budget(self):
        result = self.workflow("d['relations']=[]", max_repairs=2)
        self.assertEqual(len(result['state']['editor_attempts']), 3)
        self.assertEqual(result['state']['editor_attempt']['validation']['status'], 'REPAIR_REQUIRED')
        self.error('HANDOFF_REPAIR_REQUIRED', candidate_proposal, result['state'])
        self.assertEqual(result['state']['effects'], {})
        self.assertEqual(sum(c['format']=='verantyx.editor-request.v1' for c in self.fixture.invocations()), 3)

    def test_same_adapter_is_rejected_before_model_call_or_task_record(self):
        vera, _ = self.adapters()
        self.error('EDITOR_ROLE_COLLISION', ask, self.root, self.cfg, request='Work', adapter_path=vera, editor_adapter=vera, key='bad')
        self.assertEqual(self.fixture.invocations(), [])

    def test_new_api_config_path_does_not_make_same_model_independent(self):
        from verantyx.coordination import separate_models
        model={'provider':'ollama','model':'same','endpoint':'http://127.0.0.1:11434/api/generate'}
        with mock.patch('verantyx.adapters.command_process.load_command', side_effect=[{'identity':'a','model_api':model},{'identity':'b','model_api':model}]), \
             mock.patch('verantyx.jobs._executor_fingerprint', side_effect=['a','b']):
            self.error('EDITOR_ROLE_COLLISION', separate_models, 'a', 'b')

    def test_all_older_originals_survive_beyond_four_turns(self):
        adapter = self.fixture.adapter()
        parent = None
        for i in range(7):
            result = ask(self.root, self.cfg, request='original-'+str(i), adapter_path=adapter, key='turn-'+str(i),
                         run_id='turn-'+str(i), continue_from=parent)
            parent = result['state']['run_id']
        sources = self.fixture.invocations()[-1]['shared_context']['sources']
        self.assertEqual([s['text'] for s in sources], ['original-'+str(i) for i in range(7)])

    def test_context_scope_widening_is_rejected(self):
        adapter = self.fixture.adapter()
        ask(self.root, self.cfg, request='original', adapter_path=adapter, key='first', run_id='first')
        self.error('SHARED_CONTEXT_SCOPE', ask, self.root, self.cfg, request='new', adapter_path=adapter, key='new',
                   context={'component':'new','workload':'UNSPECIFIED','risk':'HIGH'}, continue_from='first')
        self.assertEqual(len(self.fixture.invocations()), 2)

    def test_source_tampering_is_rejected_without_relying_only_on_packet_hash(self):
        state = self.workflow()['state']
        packet = deepcopy(state['shared_context'])
        packet['sources'][0]['text']='Cancelled.'
        packet['sha256']=digest({k:v for k,v in packet.items() if k!='sha256'})
        self.error('SHARED_CONTEXT_INVALID', validate_packet, packet)

    def test_fabricated_quote_and_source_omission_are_rejected(self):
        state = self.workflow()['state']
        packet, plan = state['shared_context'], deepcopy(state['handoff_plan']['plan'])
        plan['interpretations'][0]['quote']='never said this'
        self.error('SHARED_CONTEXT_SOURCE', validate_plan, plan, packet)
        packet = deepcopy(packet)
        source=deepcopy(packet['sources'][0]); source['id']=source['source_ref']='extra-source'
        packet['sources'].append(source)
        plan=deepcopy(state['handoff_plan']['plan'])
        self.error('SHARED_CONTEXT_OMITTED', validate_plan, plan, packet)

    def test_case_disagreement_and_missing_ack_are_not_success(self):
        state = self.workflow()['state']
        packet, plan, editor = state['shared_context'], state['handoff_plan']['plan'], deepcopy(state['editor_attempt']['document'])
        editor['case_choices'][0]['choice']='cancel'
        editor['acknowledgements'].pop()
        validate_editor(editor,packet,plan)
        result=compare(comparison_inputs(packet,plan,editor))
        self.assertIn('case:sequence', result['mismatch_ids'])
        self.assertIn('later:disposition', result['mismatch_ids'])
        self.assertEqual(result['mode'], 'CROSS_VM')

    def test_unanimous_unresolved_is_still_not_a_ready_candidate(self):
        state=self.workflow()['state']; plan=deepcopy(state['handoff_plan']['plan']); editor=deepcopy(state['editor_attempt']['document'])
        plan['interpretations'][0]['disposition']='UNRESOLVED'; editor['acknowledgements'][0]['disposition']='UNRESOLVED'
        result=compare(comparison_inputs(state['shared_context'],plan,editor))
        self.assertIn('now-0:resolved', result['mismatch_ids'])
        self.assertEqual(result['status'],'REPAIR_REQUIRED')

    def test_cross_geometry_includes_exception_edges_and_conjunction_cases(self):
        state=self.workflow()['state']; plan=deepcopy(state['handoff_plan']['plan']); editor=deepcopy(state['editor_attempt']['document'])
        plan['relations'].extend([{'kind':'EXCEPTION_TO','from':'later','to':'now-0'}, {'kind':'DEPENDS_ON','from':'later','to':'now-0'}])
        editor['relations']=deepcopy(plan['relations'])
        result=compare(comparison_inputs(state['shared_context'],plan,editor))
        slots=result['structure']['十字']['場所']
        self.assertEqual(slots['+z/辺/北東'], [plan['relations'][1]])
        self.assertEqual(slots['+y/辺/北東'], [plan['relations'][2]])
        self.assertEqual(slots['+x/頂点/北東端'], plan['cases'])
        self.assertEqual(result['status'],'MATCHED')

    def test_duplicate_and_replay_do_not_call_models_or_cross(self):
        first=self.workflow()
        second=ask(self.root,self.cfg,request='Connect first; independence is deferred.', adapter_path=self.root/'vera.json',
                   editor_adapter=self.root/'editor.json',include_paths=['calc.py','test_calc.py'],key='work',run_id='work')
        self.assertEqual(first['projection_hash'],second['projection_hash'])
        self.assertEqual(len(self.fixture.invocations()),4)
        with EventStore(self.root,self.cfg['project']['id']) as store:
            events=store.events('work')
        with mock.patch('subprocess.run',side_effect=AssertionError('replay ran a process')):
            state=replay(events)
        self.assertEqual(state['editor_attempt'],first['state']['editor_attempt'])

    def test_cross_missing_is_explicit_and_does_not_claim_semantic_proof(self):
        state=self.workflow()['state']
        inputs=comparison_inputs(state['shared_context'],state['handoff_plan']['plan'],state['editor_attempt']['document'])
        result=compare(inputs,binary=self.root/'not-present')
        self.assertEqual(result['mode'],'HOST_FALLBACK')
        self.assertEqual(result['semantic_fidelity'],'UNPROVEN')
        self.assertFalse(result['execution_authorized'])
        mutated=deepcopy(result); mutated['status']='REPAIR_REQUIRED'
        self.error('SHARED_CONTEXT_INVALID',validate_result,mutated,inputs)

    def test_candidate_cannot_change_the_pinned_test_or_inject_authority(self):
        state=self.workflow()['state']; editor=deepcopy(state['editor_attempt']['document'])
        editor['files']['test_calc.py']='print("OK")'
        self.error('TEST_SCOPE',validate_editor,editor,state['shared_context'],state['handoff_plan']['plan'])
        editor=deepcopy(state['editor_attempt']['document']); editor['approved']=True
        self.error('SHARED_CONTEXT_INVALID',validate_editor,editor,state['shared_context'],state['handoff_plan']['plan'])

    def test_overflow_stops_instead_of_dropping_the_oldest_source(self):
        state=self.workflow()['state']; packet=deepcopy(state['shared_context'])
        source=packet['sources'][0]
        packet['sources']=[{**source,'id':'id-'+str(i),'source_ref':'id-'+str(i)} for i in range(65)]
        packet['sha256']=digest({k:v for k,v in packet.items() if k!='sha256'})
        self.error('SHARED_CONTEXT_LIMIT',validate_packet,packet)

    def test_new_commands_remain_inside_authority_gate(self):
        from verantyx.cli import main
        import contextlib,io
        for command in (['handoff-editor','work','--adapter','a','--editor-adapter','b','--key','x','--expected-revision','1'],
                        ['editor-candidate','work','--key','x','--expected-revision','1']):
            with mock.patch('verantyx.authority.state',return_value={'enabled':True}),contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertNotEqual(main(['--project',str(self.root),'--json',*command]),0)
            self.assertEqual(json.loads(out.getvalue())['error']['code'],'AUTHORITY_REQUIRED')

    def test_same_source_different_interpretation_text_is_not_claimed_as_proved(self):
        state=self.workflow()['state']; editor=deepcopy(state['editor_attempt']['document'])
        editor['acknowledgements'][0]['interpretation']='A misleading prose explanation despite matching labels.'
        result=compare(comparison_inputs(state['shared_context'],state['handoff_plan']['plan'],editor))
        self.assertEqual(result['status'],'MATCHED')
        self.assertEqual(result['semantic_fidelity'],'UNPROVEN')
        self.assertFalse(result['execution_authorized'])

    def test_proposal_only_does_not_stage_writer_action_and_cannot_be_replayed_as_execution(self):
        vera,editor=self.adapters()
        args=dict(request='Connect first.',adapter_path=vera,editor_adapter=editor,key='proposal-only',
                  include_paths=['calc.py','test_calc.py'],max_repairs=0)
        result=ask(self.root,self.cfg,proposal_only=True,**args)
        self.assertEqual(result['state']['editor_attempt']['validation']['status'],'MATCHED')
        self.assertEqual({action['tool_id'] for action in result['state']['proposal']['actions']},{'file.observe'})
        self.assertEqual(result['state']['effects'],{})
        self.error('IDEMPOTENCY_CONFLICT',ask,self.root,self.cfg,**args)
        self.error('ARGUMENTS',ask,self.root,self.cfg,proposal_only=True,auto_check=True,**args)

    def test_actual_isolated_execution_uses_editors_files_and_frozen_tests(self):
        result=self.workflow(context={'component':'calculator','workload':'fixture','risk':'LOW'})
        for args in (['init','-q'], ['add','calc.py','test_calc.py'],
                     ['-c','user.name=Protocol fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixed test and broken implementation']):
            subprocess.run(['git','-C',str(self.root),*args],check=True,capture_output=True)
        from verantyx.cli import parse
        from verantyx.application import dispatch
        _, args=parse(['decide','work','--point','editor-isolation','--choice','isolate',
                      '--reason','ARTIFICIAL FIXTURE, not an actual user decision','--key','fixture-decision',
                      '--expected-revision',str(result['recorded_revision'])])
        dispatch(self.root,self.cfg,args,'ja')
        from verantyx.effects import authorize, execute
        precedent=os.environ['VERANTYX_PRECEDENT']
        authorized=authorize(self.root,self.cfg,'work','editor-apply',precedent,'fixture-permission')
        executed=execute(self.root,self.cfg,'work',authorized['lease_id'],precedent,'fixture-execute')
        effect=executed['state']['effects'][authorized['lease_id']]
        self.assertEqual(effect['status'],'CANDIDATE_TESTED')
        self.assertEqual(effect['receipt']['verification']['closure'],'BOUNDED')
        self.assertFalse(effect['receipt']['verification']['adoption_authorized'])
        self.assertEqual(self.root.joinpath('calc.py').read_text(),'def answer():\n    return 1\n')
        candidate=Path(effect['lease']['resource_scope'])/'calc.py'
        self.assertEqual(candidate.read_text(),'def answer():\n    return 2\n')
        from verantyx.coordination import editor_request
        packet=editor_request(executed['state'],[],None)
        self.assertEqual(packet['recorded_execution_results'][0]['status'],'CANDIDATE_TESTED')

    def test_edit_body_cannot_be_swapped_after_matched_handoff(self):
        state=self.workflow()['state']
        from verantyx.domain.effects import editor_binding
        action=deepcopy(state['proposal']['actions'][0]);action['arguments']['files']['calc.py']='wrong'
        self.error('SHARED_CONTEXT_STALE',editor_binding,state,action)

    def test_selected_source_change_cannot_be_hidden_by_new_observation(self):
        state=self.workflow()['state']
        from verantyx.coordination import assert_editor_sources
        self.root.joinpath('calc.py').write_text('another agent changed this')
        self.error('PROPOSAL_CONTEXT',assert_editor_sources,self.root,state)
        updated=record_run(self.root,self.cfg,run_id='work',resume=True,key='refresh')
        self.error('SHARED_CONTEXT_STALE',assert_editor_sources,self.root,updated['state'])

    def test_interruption_after_editor_record_resumes_without_repeated_calls(self):
        from verantyx.coordination import append as real_append
        def interrupted(*args,**kwargs):
            value=real_append(*args,**kwargs)
            if args[3]=='EditorAttemptRecorded':
                raise RuntimeError('fixture interruption after durable record')
            return value
        with mock.patch('verantyx.coordination.append',side_effect=interrupted),self.assertRaises(RuntimeError):
            self.workflow()
        self.assertEqual(len(self.fixture.invocations()),3)
        result=ask(self.root,self.cfg,request='Connect first; independence is deferred.',adapter_path=self.root/'vera.json',
                   editor_adapter=self.root/'editor.json',include_paths=['calc.py','test_calc.py'],key='work',run_id='work')
        self.assertEqual(result['state']['editor_attempt']['validation']['status'],'MATCHED')
        self.assertEqual(len(self.fixture.invocations()),4)

    def test_editor_transport_failure_is_not_automatically_retried(self):
        with self.assertRaises(LedgerError):
            self.workflow('raise SystemExit(7)')
        count=len(self.fixture.invocations())
        with self.assertRaises(LedgerError):
            ask(self.root,self.cfg,request='Connect first; independence is deferred.',adapter_path=self.root/'vera.json',
                editor_adapter=self.root/'editor.json',include_paths=['calc.py','test_calc.py'],key='work',run_id='work')
        self.assertEqual(count,3)
        self.assertEqual(len(self.fixture.invocations()),count)

    def test_generation_schemas_keep_roles_and_reject_added_authority(self):
        self.workflow()
        import jsonschema
        from verantyx.ollama_schema import output_schema
        for request in self.fixture.invocations()[1:3]:
            schema=output_schema(request)
            jsonschema.Draft202012Validator.check_schema(schema)
            self.assertFalse(schema['additionalProperties'])
            self.assertNotIn('approved',schema['properties'])

    def test_real_http_adapter_accepts_both_new_protocols_and_reserves_context(self):
        result=self.workflow()
        from test_model_connections import HTTPFixture
        from verantyx.model_api import request as api_request, payload
        server=HTTPFixture()
        self.addCleanup(server.close)
        requests=deepcopy(self.fixture.invocations()[1:3])
        requests[0]['response_template']=result['state']['handoff_plan']['plan']
        requests[1]['response_template']=result['state']['editor_attempt']['document']
        for value in requests:
            response=api_request(server.configuration('ollama'), value)
            self.assertEqual(response,value['response_template'])
        self.assertEqual(len(server.calls),2)

        self.assertEqual(list(server.calls[0]['body']['format']['properties']),
                         ['context_sha256', 'interpretations', 'relations', 'cases'])
        self.assertGreaterEqual(server.calls[1]['body']['options']['num_ctx'],8192)
        oversized=deepcopy(requests[0]);oversized['extra']='x'*65536
        self.error('SHARED_CONTEXT_LIMIT',payload,server.configuration('ollama'),oversized)
        self.assertEqual(len(server.calls),2)

    def test_legacy_ask_journal_can_finish_without_changing_its_old_intent(self):
        from verantyx.adapters.invocation_journal import InvocationJournal
        adapter = self.fixture.adapter()
        intent = dict(request='Legacy request', adapter=str(adapter), key='legacy', run_id='legacy',
                      include_paths=[], locale=None, context=None, reuse_assets=True, timeout=60,
                      project_id=self.cfg['project']['id'])
        with InvocationJournal(self.root, 'ask', 'legacy') as journal:
            journal.write('started', {'intent_hash': digest(intent), 'run_id': 'legacy'})
        result = ask(self.root, self.cfg, request='Legacy request', adapter_path=adapter,
                     key='legacy', run_id='legacy')
        self.assertFalse(result['state'].get('shared_context'))
        duplicate = ask(self.root, self.cfg, request='Legacy request', adapter_path=adapter,
                        key='legacy', run_id='legacy')
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(len(self.fixture.invocations()), 2)
        self.error('IDEMPOTENCY_CONFLICT', ask, self.root, self.cfg, request='Legacy request',
                   adapter_path=adapter, key='legacy', run_id='legacy', continue_from='other')

    def test_failed_generation_keeps_original_for_next_turn(self):
        from verantyx.console import recorded_context_run
        broken = self.fixture.adapter('raise SystemExit(3)', filename='broken')
        with self.assertRaises(LedgerError):
            ask(self.root, self.cfg, request='Never overwrite my original.',
                adapter_path=broken, key='failed', run_id='failed')
        parent = recorded_context_run(self.root, self.cfg, 'failed')
        self.assertEqual(parent, 'failed')
        result = ask(self.root, self.cfg, request='Continue with another model.',
                     adapter_path=self.fixture.adapter(), key='next', run_id='next', continue_from=parent)
        self.assertEqual([s['text'] for s in result['state']['shared_context']['sources']],
                         ['Never overwrite my original.', 'Continue with another model.'])
        self.assertIsNone(recorded_context_run(self.root, self.cfg, 'missing'))

    def test_public_context_inspection_explains_interpretations_in_five_languages(self):
        self.workflow()
        from verantyx.i18n import LANGUAGES, text
        for language in LANGUAGES:
            completed = subprocess.run([sys.executable, '-m', 'verantyx', '--project', str(self.root),
                                       '--lang', language, 'shared-context', 'work'],
                                      capture_output=True, text=True, timeout=20)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn('Connect first; independence is deferred.', completed.stdout)
            self.assertIn(text(language, 'context.DEFERRED'), completed.stdout)
            self.assertIn(text(language, 'context.boundary'), completed.stdout)
            self.assertNotIn('DEFERRED', completed.stdout)

    def test_generation_requires_each_ack_but_does_not_force_semantic_agreement(self):
        result = self.workflow()
        from jsonschema import Draft202012Validator
        from verantyx.coordination_schema import schema
        request = self.fixture.invocations()[2]
        validator = Draft202012Validator(schema(request))
        document = deepcopy(result['state']['editor_attempt']['document'])
        self.assertTrue(validator.is_valid(document))
        document['acknowledgements'][-1]['disposition'] = 'FORBIDDEN'
        self.assertTrue(validator.is_valid(document))
        self.assertEqual(compare(comparison_inputs(result['state']['shared_context'],
                         result['state']['handoff_plan']['plan'], document))['status'], 'REPAIR_REQUIRED')
        document['acknowledgements'].pop()
        self.assertFalse(validator.is_valid(document))

    def test_editor_relation_schema_rejects_claim_ids_and_self_links(self):
        from jsonschema import Draft202012Validator
        from verantyx.coordination_schema import relation_schema
        validator = Draft202012Validator(relation_schema(['intent-1', 'intent-2']))
        self.assertTrue(validator.is_valid([{'kind':'DEPENDS_ON','from':'intent-1','to':'intent-2'}]))
        for source, target in [('claim-001','intent-1'), ('intent-1','intent-1')]:
            self.assertFalse(validator.is_valid([{'kind':'DEPENDS_ON','from':source,'to':target}]))
        single = Draft202012Validator(relation_schema(['intent-1']))
        self.assertTrue(single.is_valid([]))
        self.assertFalse(single.is_valid([{'kind':'DEPENDS_ON','from':'claim-001','to':'intent-1'}]))

    def test_citation_slots_preserve_multilingual_text_and_group_at_the_limit(self):
        from verantyx.coordination_schema import source_units
        request = {'shared_context': {'sources': [{'id': 'original', 'text': '先に接続する。独立性は後で、例外は残す。\nKeep the original; defer optimization.'}]}}
        units = source_units(request)
        for unit in units:
            self.assertIn(unit['quote'], request['shared_context']['sources'][0]['text'])
            self.assertEqual(unit['source_id'], 'original')
        self.assertIn('独立性は後で、', [u['quote'] for u in units])
        request['shared_context']['sources'][0]['text'] = 'case;' * 65
        grouped = source_units(request)
        self.assertEqual(len(grouped), 64)
        self.assertEqual(''.join(unit['quote'] for unit in grouped), 'case;' * 65)

    def test_source_line_transport_preserves_code_escapes_and_line_endings(self):
        result = self.workflow()
        from verantyx.coordination_schema import encode_editor_document, decode_editor_document
        request = self.fixture.invocations()[2]
        for body in ('print("\\n")\n', '# 日本語\r\nx = 2\r\n', '', '\n', 'x = 2'):
            document = deepcopy(result['state']['editor_attempt']['document'])
            document['files']['calc.py'] = body
            encoded = encode_editor_document(document)
            self.assertEqual(decode_editor_document(encoded, request), document)
        encoded['file_line_blocks']['calc.py']['lines'] = ['x = 2\ny = 3']
        self.error('SHARED_CONTEXT_INVALID', decode_editor_document, encoded, request)

    def test_compact_plan_preserves_quotes_and_all_generated_fields_and_reject_omissions(self):
        from verantyx.coordination_schema import source_units, decode_plan_compact
        packet = {'sha256': '0' * 64, 'sources': [{'id': 'first', 'text': '\n' + ''.join(str(i) + ': 原文。例外も残す。\r\n' for i in range(40))},
                  {'id': 'second', 'text': 'Connection first; independence later. 🙂'}]}
        value = {'format': 'verantyx.handoff-plan-request.v1', 'shared_context': packet}
        units = source_units(value)
        rows = {'context_sha256': '0' * 64,
                'interpretation_values': [{'quote':u['quote'], 'meaning':'Meaning ' + u['id'], 'disposition':'UNRESOLVED', 'strength':'OPEN', 'alternatives':['Another reading.']} for u in units],
                'relations': [{'kind': 'PRIORITY_OVER', 'from': units[0]['id'], 'to': units[-1]['id']}],
                'case_values': [{'situation':'Situation ' + str(i), 'choices':[{'text':'Keep.'},{'text':'Remove.'}], 'expected':'choice-B'} for i in range((len(units) + 1) // 2)]}
        decoded = decode_plan_compact(rows, value)
        validate_plan(decoded, packet)
        self.assertEqual(len(decoded['interpretations']), 64)
        self.assertEqual(len(decoded['cases']), 32)
        self.assertEqual(decoded['relations'], rows['relations'])
        for source in packet['sources']:
            self.assertEqual(''.join(n['quote'] for n in decoded['interpretations'] if n['source_id'] == source['id']), source['text'])
        for unit, row, node in zip(units, rows['interpretation_values'], decoded['interpretations']):
            self.assertEqual(node, {**unit, **row})
        for i, case in enumerate(decoded['cases']):
            self.assertEqual(case['expected'], 'choice-B')
            self.assertEqual(case['interpretation_ids'], [u['id'] for u in units[2 * i:2 * i + 2]])
            self.assertEqual(case['choices'], [{'id': 'choice-A', 'text': 'Keep.'}, {'id': 'choice-B', 'text': 'Remove.'}])
        for mutate in (lambda x: x['interpretation_values'].pop(), lambda x: x['interpretation_values'].reverse(),
                       lambda x: x['interpretation_values'][0].__setitem__('quote', 'forged quote'),
                       lambda x: x['interpretation_values'][0].pop('meaning'), lambda x: x['case_values'].pop(),
                       lambda x: x.update(approved=True)):
            bad = deepcopy(rows)
            mutate(bad)
            self.error('SHARED_CONTEXT_INVALID', decode_plan_compact, bad, value)

    def test_real_model_counterexample_cannot_omit_the_deferred_conditions_from_cases(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/shared-context-counterexample.json').read_text())
        inputs = comparison_inputs(fixture['packet'], fixture['plan'], fixture['editor'])
        result = compare(inputs)
        self.assertEqual(result['status'], 'REPAIR_REQUIRED')
        self.assertEqual(result['mismatch_ids'], ['intent-3:case_covered', 'intent-4:case_covered'])
        self.assertEqual(result['semantic_fidelity'], 'UNPROVEN')


if __name__=='__main__':
    unittest.main()
