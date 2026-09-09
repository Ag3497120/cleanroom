"""Source-literal binding is finite evidence, never a prose truth oracle.

All requests, imported references, model documents and ledgers below are
artificial and temporary. Numeric 43 is taken from the saved 0.7.1 probe.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from unittest import mock
import unittest

import test_asset_workflow_v070 as fixture
from verantyx.application import record_run
from verantyx.assets import project_assets
from verantyx.domain.asset_workflow import compile_document, expectation_bindings
from verantyx.domain.codec import decode, digest
from verantyx.domain.verification import check_input, _pointer
from verantyx.errors import LedgerError
from verantyx.external_capture import capture
from verantyx.kernel.reducer import replay


QUOTE = '検査条件の引用：JSONの /answer は数値の43に等しい必要があります。文字列や別の数値では条件を満たしません。'
REQUEST = '明示して取り込んだ外部メモの条件に対して、report.jsonのanswerをJSONの値として検査してください。外部メモは未検証の引用です。'


MODEL = fixture.MODEL.replace("steps=[s]", """
source=c['external_captures'][0]
s['checks'][0]['expected']=43
s['source_refs']=[source['source_ref']]
s['expectation_basis']=source['body']
if mode=='wrapper' or (mode=='repair-wrapper' and n==1):
    s['checks'][0]['expected']={'type':'integer','value':43}
if mode=='object':s['checks'][0]['expected']={'type':'integer','value':43}
if mode=='target-only':s['source_refs']=[c['selected_files'][0]['source_ref']]
if mode=='string':s['checks'][0]['expected']='43'
steps=[s]
""")


class ExpectationBindingTests(unittest.TestCase):
    setUp = fixture.AssetWorkflowTests.setUp
    tearDown = fixture.AssetWorkflowTests.tearDown
    adapter_mode = fixture.AssetWorkflowTests.adapter_mode
    call = fixture.AssetWorkflowTests.call
    events = fixture.AssetWorkflowTests.events

    def request(self, name, paths=('report.json',)):
        result = record_run(self.root, self.cfg, request=REQUEST, run_id=name, observe_paths=paths, clock=self.clock)
        proposal = {'schema_version':1, 'task_id':name, 'context_revision':result['recorded_revision'],
                    'response_locale':'ja', 'summary':'An artificial source-grounded check.',
                    'claims':[{'id':'answer', 'statement':'answer agrees with the imported reference.',
                               'source_refs':[result['state']['request_ref']]}], 'actions':[], 'unknowns':[]}
        path = self.root / (name+'-proposal.json')
        path.write_text(json.dumps(proposal))
        return record_run(self.root, self.cfg, run_id=name, proposal_path=path, resume=True, clock=self.clock)

    def prepare(self, body=QUOTE, mode='compile', answer=43):
        (self.root/'report.json').write_text(json.dumps({'answer':answer}, ensure_ascii=False))
        state = record_run(self.root, self.cfg, run_id='first', resume=True, clock=self.clock)['state']
        quoted = capture(self.root, self.cfg, 'first', body=body, provider='artificial-reference', model='fixture',
                         key='source', expected_revision=state['revision'], clock=self.clock)
        self.script.write_text(MODEL)
        self.adapter_mode(mode)
        return quoted['state']['external_captures'][0]

    def test_saved_real_model_error_reproduces_before_new_context_contract(self):
        old = json.loads((Path(__file__).resolve().parents[1]/'validation/live-reference-v071.json').read_text())
        context = old['first_workflow']['plan']['context']
        document = old['first_workflow']['plan']['document']
        compiled = compile_document(context, document, 1)
        check = compiled[0]['spec']['checks']
        self.assertFalse(check_input(b'{"answer":43}', check)[0]['passed'])
        self.assertTrue(check_input(b'{"answer":{"type":"integer","value":43}}', check)[0]['passed'])
        revised = deepcopy(context)
        revised['expectation_binding_version'] = 1
        changed = deepcopy(document)
        changed['context_sha256'] = digest(revised)
        with self.assertRaises(LedgerError) as error:
            compile_document(revised, changed, 1)
        self.assertEqual(error.exception.details['reason'], 'EXPECTATION_SOURCE_REQUIRED')
        changed['steps'][0]['source_refs'] = [revised['external_captures'][0]['source_ref']]
        with self.assertRaises(LedgerError) as error:
            compile_document(revised, changed, 1)
        self.assertEqual(error.exception.details['reason'], 'EXPECTATION_LITERAL_MISMATCH')

    def test_numeric_source_binds_exact_type_and_value_without_truth_promotion(self):
        quote = self.prepare()
        result = self.call()
        step = result['workflow']['plan']['steps'][0]
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        binding = step['expectation_bindings'][0]
        self.assertEqual(binding['source_ref'], quote['source_ref'])
        self.assertEqual(binding['source_sha256'], quote['body_sha256'])
        self.assertEqual(binding['offset_unit'], 'UNICODE_CODEPOINT')
        self.assertEqual(quote['body'][binding['start']:binding['end']], '43')
        self.assertEqual(binding['literal_type'], 'integer')
        self.assertEqual(binding['relationship'], 'LITERAL_MATCH_ONLY')
        self.assertEqual(step['expectation_origin'], 'MODEL_PROPOSED')
        self.assertEqual(step['prose_entailment'], 'NOT_ASSESSED')
        self.assertEqual(step['independence'], 'NOT_ESTABLISHED')
        self.assertFalse(result['authority_granted'])
        self.assertEqual(result['state']['human_decisions'], {})
        self.assertEqual(result['state']['effects'], {})
        checks = step['spec']['checks']
        for answer, passed in [(43,True), (7,False), ('43',False), ({'type':'integer','value':43},False)]:
            with self.subTest(answer=answer):
                self.assertEqual(check_input(json.dumps({'answer':answer}).encode(),checks)[0]['passed'],passed)

    def test_wrong_wrapper_is_retained_as_rejection_and_repaired_before_verification(self):
        self.prepare(mode='repair-wrapper')
        result = self.call()
        plan = result['workflow']['plan']
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(plan['rejected'][0]['reason'], 'EXPECTATION_LITERAL_MISMATCH')
        sent = json.loads((self.root / 'model-input.json').read_text())
        self.assertEqual(sent['repair_feedback']['rejected_document']['steps'][0]['checks'][0]['expected'],
                         {'type': 'integer', 'value': 43})
        self.assertEqual(len(result['state']['verifications']), 1)
        self.assertEqual(plan['steps'][0]['spec']['checks'][0]['expected'], 43)
        self.assertEqual(len(project_assets(result['state'])['verification_methods']), 1)
        stored = list((self.root/'.verantyx/bridges').glob('*.round-1-response.json'))
        self.assertEqual(len(stored), 1)
        import base64
        original = json.loads(base64.b64decode(json.loads(stored[0].read_text())['raw_base64']))
        self.assertEqual(original['steps'][0]['checks'][0]['expected'], {'type':'integer','value':43})
        self.assertEqual(plan['rejected'][0]['response_sha256'], hashlib.sha256(base64.b64decode(json.loads(stored[0].read_text())['raw_base64'])).hexdigest())

    def test_ungrounded_value_does_not_create_an_executable_asset(self):
        for mode in ('wrapper','string','target-only'):
            with self.subTest(mode=mode):
                if mode == 'wrapper':
                    self.prepare(mode=mode)
                else:
                    self.adapter_mode(mode)
                result = self.call(key='reject-'+mode)
                self.assertEqual(result['workflow']['status'], 'NO_PLAN')
                self.assertEqual(result['state'].get('verifications', {}), {})
                self.assertEqual(project_assets(result['state'])['verification_methods'], [])
                self.assertEqual(len(result['workflow']['plan']['rejected']), 2)

    def test_explicit_object_literal_remains_a_valid_equality_requirement(self):
        body = 'JSON /answer の要求値は {"type": "integer", "value": 43} です。'
        self.prepare(body=body, mode='object', answer={'type':'integer','value':43})
        result = self.call()
        step = result['workflow']['plan']['steps'][0]
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        binding = step['expectation_bindings'][0]
        self.assertEqual(binding['literal_type'], 'object')
        self.assertEqual(binding['source_pointer'], '')
        self.assertEqual(decode(body[binding['start']:binding['end']]), {'type':'integer','value':43})
        self.assertFalse(check_input(b'{"answer":43}', step['spec']['checks'])[0]['passed'])

    def test_literal_inside_source_json_keeps_its_source_pointer(self):
        body = '{"condition":{"a/b~c":43},"approved":true}'
        self.prepare(body=body)
        result = self.call()
        binding = result['workflow']['plan']['steps'][0]['expectation_bindings'][0]
        self.assertEqual(binding['source_pointer'], '/condition/a~1b~0c')
        self.assertEqual(_pointer(decode(body[binding['start']:binding['end']]), binding['source_pointer']), 43)
        self.assertFalse(result['authority_granted'])

    def test_quoted_numeric_string_does_not_bind_numeric_expectation(self):
        self.prepare(body='JSON /answer の値は "43" です。')
        result = self.call()
        self.assertEqual(result['workflow']['status'], 'NO_PLAN')
        self.assertEqual(result['workflow']['plan']['rejected'][0]['reason'], 'EXPECTATION_LITERAL_MISMATCH')

    def test_literal_presence_elsewhere_does_not_claim_prose_entailment(self):
        # This intentionally demonstrates the boundary of the finite check:
        # a model can pick an irrelevant literal in an otherwise cited source.
        self.prepare(body='例番号43。実際の /answer は7にしてください。')
        result = self.call()
        step = result['workflow']['plan']['steps'][0]
        self.assertEqual(step['expectation_bindings'][0]['relationship'], 'LITERAL_MATCH_ONLY')
        self.assertEqual(step['prose_entailment'], 'NOT_ASSESSED')
        self.assertEqual(step['independence'], 'NOT_ESTABLISHED')
        self.assertEqual(step['expectation_origin'], 'MODEL_PROPOSED')
        self.assertFalse(result['authority_granted'])

    def test_replay_rejects_changed_binding_without_reading_original_files(self):
        self.prepare()
        result = self.call()
        events = self.events('first')
        with mock.patch('builtins.open', side_effect=AssertionError('replay read source')), mock.patch('subprocess.run', side_effect=AssertionError('replay called verifier')):
            self.assertEqual(replay(events)['asset_workflows'], result['state']['asset_workflows'])
        from verantyx.domain.asset_workflow import validate_payload
        payload = deepcopy(result['workflow']['plan'])
        payload['steps'][0]['expectation_bindings'][0]['start'] += 1
        with self.assertRaises(LedgerError) as error:
            validate_payload('AssetWorkflowPlanned', payload)
        self.assertEqual(error.exception.details['reason'], 'COMPILED_SPEC_CHANGED')

    def test_old_unbound_model_contract_is_not_automatically_reused_as_a_goal(self):
        self.prepare(mode='wrapper', answer={'type':'integer','value':43})
        import verantyx.asset_workflow as workflow
        original = workflow._context
        def old_context(*args, **kwargs):
            result = original(*args, **kwargs)
            result.pop('expectation_binding_version', None)
            return result
        with mock.patch.object(workflow, '_context', side_effect=old_context):
            old = self.call(key='legacy-wrapper')
        self.assertEqual(old['workflow']['status'], 'COMPLETED')
        self.assertEqual(old['workflow']['plan']['steps'][0]['spec']['provenance']['oracle'], 'MODEL_PROPOSED_NOT_INDEPENDENT')
        self.request('second')
        self.script.write_text(fixture.MODEL)
        self.adapter_mode('reuse')
        result = self.call('second', key='automatic-reuse')
        self.assertEqual(result['workflow']['status'], 'NO_PLAN')
        self.assertEqual(result['workflow']['plan']['rejected'][0]['reason'], 'EXPECTATION_SOURCE_REQUIRED')
        self.assertEqual(result['state'].get('verifications', {}), {})
        self.assertFalse(result['authority_granted'])
        # The old record remains replayable with its original limited status.
        self.assertEqual(replay(self.events('first'))['asset_workflows'], old['state']['asset_workflows'])

    def test_bound_contract_can_be_reused_without_a_model(self):
        self.prepare()
        first = self.call()
        asset = project_assets(first['state'])['verification_methods'][0]
        self.request('second')
        from verantyx.asset_workflow import run_asset_workflow
        second = run_asset_workflow(self.root, self.cfg, 'second', reuse_asset=asset['id'], claim_id='answer',
                                    target_path='report.json', key='explicit', clock=self.clock)
        self.assertEqual(second['workflow']['status'], 'COMPLETED')
        self.assertEqual(second['model_calls'], 0)
        self.assertEqual(first['workflow']['plan']['steps'][0]['spec']['checks'], second['workflow']['plan']['steps'][0]['spec']['checks'])
        self.assertEqual(self.counter.read_text(), '1')
        self.assertFalse(second['authority_granted'])
        self.assertEqual(second['workflow']['results'][0]['independence'], 'NOT_ESTABLISHED')

    def test_v1_saved_binding_recompiles_to_the_original_hash(self):
        old = json.loads((Path(__file__).resolve().parents[1]/'validation/live-reference-v071.json').read_text())
        context = deepcopy(old['first_workflow']['plan']['context'])
        context['expectation_binding_version'] = 1
        document = deepcopy(old['first_workflow']['plan']['document'])
        document['context_sha256'] = digest(context)
        document['steps'][0]['checks'][0]['expected'] = 43
        document['steps'][0]['source_refs'] = [context['external_captures'][0]['source_ref']]
        self.assertEqual(digest(compile_document(context, document, 1)),
                         '99cb126d751d0dcd2d016e87fd463815f18ef0f5856f2871ba9ee212cb6443cf')

    def test_switching_predicates_cannot_supply_an_expectation_absent_from_sources(self):
        self.prepare()
        for kind, expected in [('bytes.sha256', '0'*64), ('bytes.size', 999),
                               ('text.equals', 'fabricated'), ('text.contains', 'fabricated'),
                               ('json.type', 'integer')]:
            with self.subTest(kind=kind):
                pointer = '/answer' if kind.startswith('json.') else ''
                replacement = "s['checks'][0]="+repr({'id':'answer','kind':kind,'pointer':pointer,'expected':expected})+"\nsteps=[s]"
                self.script.write_text(MODEL.replace('steps=[s]', replacement))
                result = self.call(key='escape-'+kind)
                self.assertEqual(result['workflow']['status'], 'NO_PLAN')
                self.assertEqual(result['workflow']['plan']['rejected'][0]['reason'], 'EXPECTATION_LITERAL_MISMATCH')
                self.assertEqual(result['state'].get('verifications', {}), {})

    def test_sha_escape_is_retained_then_repaired_to_the_original_json_value(self):
        self.prepare()
        self.script.write_text(MODEL.replace('steps=[s]',
            "if n==1:s['checks'][0]={'id':'answer','kind':'bytes.sha256','pointer':'','expected':'0'*64}\nsteps=[s]"))
        result = self.call()
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(result['workflow']['plan']['rejected'][0]['reason'], 'EXPECTATION_LITERAL_MISMATCH')
        self.assertEqual(result['workflow']['plan']['steps'][0]['spec']['checks'],
                         [{'id':'answer','kind':'json.equals','pointer':'/answer','expected':43}])
        self.assertEqual(len(result['state']['verifications']), 1)

    def test_all_six_existing_predicates_keep_correct_literal_contracts(self):
        cases = [
            ('bytes.sha256', '', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
             'Expected SHA-256: ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad.', b'abc', b'abd'),
            ('bytes.size', '', 3, 'Expected byte count: 3.', b'abc', b'abcd'),
            ('text.equals', '', 'ready\n', 'Expected exact text, as JSON: "ready\\n".', b'ready\n', b'ready'),
            ('text.contains', '', 'needle', 'The required substring is needle.', b'a needle b', b'a yarn b'),
            ('json.equals', '/answer', {'state':'ready'}, 'Expected JSON object: {"state":"ready"}.', b'{"answer":{"state":"ready"}}', b'{"answer":"ready"}'),
            ('json.type', '/answer', 'integer', 'Expected JSON type is integer.', b'{"answer":43}', b'{"answer":"43"}'),
        ]
        for kind, pointer, expected, body, good, bad in cases:
            with self.subTest(kind=kind):
                context = {'expectation_binding_version':2, 'request_ref':'request', 'request':'Check the separate requirement.',
                           'external_captures':[{'source_ref':'requirement','body':body}], 'selected_files':[
                               {'source_ref':'target','path':'report.json','text':good.decode()}]}
                checks = [{'id':'required','kind':kind,'pointer':pointer,'expected':expected}]
                binding = expectation_bindings(context,checks,['requirement'],'report.json')[0]
                self.assertEqual(binding['source_ref'],'requirement')
                self.assertEqual(binding['relationship'],'LITERAL_MATCH_ONLY')
                self.assertTrue(check_input(good,checks)[0]['passed'])
                self.assertFalse(check_input(bad,checks)[0]['passed'])
                with self.assertRaises(LedgerError) as error:
                    expectation_bindings(context,checks,['target'],'report.json')
                self.assertEqual(error.exception.details['reason'],'EXPECTATION_SOURCE_REQUIRED')

    def test_fixed_json_objects_and_derived_specs_are_not_restricted(self):
        # The restriction is on new model-assisted COMPILE documents, not the
        # fixed finite verifier API or old stored contracts.
        checks = [{'id':'value','kind':'json.equals','pointer':'/answer','expected':{'derived':43}}]
        self.assertTrue(check_input(b'{"answer":{"derived":43}}',checks)[0]['passed'])


if __name__ == '__main__':
    unittest.main()
