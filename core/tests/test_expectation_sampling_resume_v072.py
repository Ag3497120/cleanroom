"""Generation contract upgrades preserve already saved model invocations.

Temporary fixture ledgers and an artificial process only. The v3 case preserves
its generic sampler; v4 has literal choices and requirement-source choices.
"""
from copy import deepcopy
import json
import unittest
from unittest import mock

import test_expectation_binding_v072 as fixture
from verantyx.adapters.invocation_journal import InvocationJournal
from verantyx.model_api import payload


class SamplingResumeTests(unittest.TestCase):
    setUp = fixture.ExpectationBindingTests.setUp
    tearDown = fixture.ExpectationBindingTests.tearDown
    request = fixture.ExpectationBindingTests.request
    prepare = fixture.ExpectationBindingTests.prepare
    adapter_mode = fixture.ExpectationBindingTests.adapter_mode
    call = fixture.ExpectationBindingTests.call
    events = fixture.ExpectationBindingTests.events

    def interrupted(self):
        def stop(stage):
            if stage == 'after_model_response':
                raise RuntimeError('Interrupted with saved artificial model response')
        with self.assertRaises(RuntimeError):
            self.call(fault=stop)
        self.assertEqual(self.counter.read_text(), '1')
        return json.loads((self.root/'model-input.json').read_text())

    def test_pre_enum_v3_saved_response_resumes_without_another_model_call(self):
        self.prepare()
        original_write = InvocationJournal.write
        def v3(journal, stage, value):
            if stage == 'started':
                # Reproduce the version written before source-value sampling
                # was introduced; keep its original input and response hashes.
                value['planning_contract_version'] = 3
            return original_write(journal, stage, value)
        with mock.patch.object(InvocationJournal, 'write', new=v3):
            sent = self.interrupted()
        props = sent['output_schema']['properties']['steps']['items']['properties']
        equality = next(row for row in props['checks']['items']['oneOf']
                        if row['properties']['kind']['const']=='json.equals')
        self.assertEqual(equality['properties']['expected'], {})
        self.assertIn(sent['context']['selected_files'][0]['source_ref'], props['source_refs']['items']['enum'])
        old = deepcopy(sent)
        result = self.call()
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        self.assertEqual(self.counter.read_text(), '1')
        self.assertEqual(json.loads((self.root/'model-input.json').read_text()), old)
        self.assertEqual(result['workflow']['plan']['steps'][0]['spec']['checks'][0]['expected'],43)

    def test_new_v4_saved_response_resumes_with_source_choices_intact(self):
        quote = self.prepare()
        sent = self.interrupted()
        self.assertEqual(sent['planning_contract_version'],4)
        props = sent['output_schema']['properties']['steps']['items']['properties']
        equality = next(row for row in props['checks']['items']['oneOf']
                        if row['properties']['kind']['const']=='json.equals')
        self.assertEqual(equality['properties']['expected'], {'enum':[43]})
        self.assertEqual(set(props['source_refs']['items']['enum']),
                         {sent['context']['request_ref'],quote['source_ref']})
        self.assertNotIn(sent['context']['selected_files'][0]['source_ref'],props['source_refs']['items']['enum'])
        self.assertEqual(sent['context']['external_captures'][0],quote)
        result = self.call()
        self.assertEqual(result['workflow']['status'],'COMPLETED')
        self.assertEqual(self.counter.read_text(),'1')
        self.assertFalse(result['authority_granted'])
        self.assertEqual(result['workflow']['results'][0]['independence'],'NOT_ESTABLISHED')

    def test_version_four_keeps_recorded_method_sources_for_automatic_reuse(self):
        self.prepare()
        original = self.call()
        import test_asset_workflow_v070 as generic_fixture
        self.script.write_text(generic_fixture.MODEL)
        self.adapter_mode('reuse')
        result = self.call(key='automatic-reuse')
        sent = json.loads((self.root/'model-input.json').read_text())
        methods = sent['context']['available_methods']
        self.assertTrue(methods)
        refs = sent['output_schema']['properties']['steps']['items']['properties']['source_refs']['items']['enum']
        self.assertIn(methods[0]['source_ref'], refs)
        self.assertNotIn(sent['context']['selected_files'][0]['source_ref'], refs)
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        self.assertEqual(result['workflow']['plan']['steps'][0]['mode'], 'REUSE')
        self.assertEqual(result['workflow']['plan']['steps'][0]['spec']['checks'],
                         original['workflow']['plan']['steps'][0]['spec']['checks'])
        self.assertFalse(result['authority_granted'])
        self.assertEqual(result['workflow']['results'][0]['independence'], 'NOT_ESTABLISHED')

    def test_ollama_order_and_extra_guidance_are_only_used_by_version_four(self):
        self.prepare()
        self.call()
        current = json.loads((self.root/'model-input.json').read_text())
        legacy = {**deepcopy(current),'planning_contract_version':3}
        config = {'provider':'ollama','model':'artificial','max_output_tokens':1024}
        old,new=payload(config,legacy),payload(config,current)
        old_fields=list(old['format']['properties']['steps']['items']['properties'])
        new_fields=list(new['format']['properties']['steps']['items']['properties'])
        self.assertLess(old_fields.index('checks'),old_fields.index('source_refs'))
        self.assertLess(new_fields.index('source_refs'),new_fields.index('checks'))
        self.assertLess(new_fields.index('expectation_basis'),new_fields.index('checks'))
        self.assertNotIn('not a required output hash',old['system'])
        self.assertIn('not a required output hash',new['system'])
        self.assertEqual(json.loads(new['prompt'])['context'],current['context'])
        self.assertEqual(json.loads(old['prompt'])['context'],legacy['context'])


if __name__=='__main__':
    unittest.main()
