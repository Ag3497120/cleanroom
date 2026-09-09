"""Independent checks of the final source-hint repair change.

Artificial process, temporary ledgers, original finite numeric reference only.
Diagnostics show literal locations; they neither repair the returned document
nor certify that prose requires a particular property.
"""
from copy import deepcopy
import base64
import json
import unittest
from unittest import mock

import test_expectation_binding_v072 as fixture
from verantyx.adapters.invocation_journal import InvocationJournal
from verantyx.assets import project_assets
from verantyx.ollama_schema import output_schema


class RepairDiagnosticTests(unittest.TestCase):
    setUp = fixture.ExpectationBindingTests.setUp
    tearDown = fixture.ExpectationBindingTests.tearDown
    request = fixture.ExpectationBindingTests.request
    prepare = fixture.ExpectationBindingTests.prepare
    adapter_mode = fixture.ExpectationBindingTests.adapter_mode
    call = fixture.ExpectationBindingTests.call
    events = fixture.ExpectationBindingTests.events

    def source_model(self, mode):
        quote = self.prepare(mode=mode)
        script = fixture.MODEL.replace("steps=[s]", """
if n==1 or mode=='wrong-request':s['source_refs']=[c['request_ref']]
steps=[s]
""")
        script = script.replace("pathlib.Path(os.environ['INPUT']).write_text(json.dumps(r))",
                                "pathlib.Path(os.environ['INPUT']).write_text(json.dumps(r)); "
                                "pathlib.Path(os.environ['INPUT']+'.'+str(n)).write_text(json.dumps(r))")
        self.script.write_text(script)
        return quote

    def sent(self, number):
        return json.loads((self.root / ('model-input.json.'+str(number))).read_text())

    def original_response(self, number):
        paths = list((self.root/'.verantyx/bridges').glob('*.round-'+str(number)+'-response.json'))
        self.assertEqual(len(paths), 1)
        return json.loads(base64.b64decode(json.loads(paths[0].read_text())['raw_base64']))

    def test_hints_do_not_accept_or_rewrite_repeated_wrong_citations(self):
        quote = self.source_model('wrong-request')
        result = self.call()
        first, second = self.sent(1), self.sent(2)
        self.assertEqual(first['context'], second['context'])
        self.assertEqual(result['workflow']['status'], 'NO_PLAN')
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(len(result['workflow']['plan']['rejected']), 2)
        self.assertEqual(result['state'].get('verifications', {}), {})
        self.assertEqual(project_assets(result['state'])['verification_methods'], [])
        self.assertFalse(result['authority_granted'])
        self.assertEqual(result['state']['human_decisions'], {})
        self.assertEqual(result['state']['effects'], {})
        raw = self.original_response(1)
        self.assertEqual(second['repair_feedback']['rejected_document'], raw)
        self.assertEqual(raw['steps'][0]['checks'][0]['expected'], 43)
        self.assertEqual(raw['steps'][0]['source_refs'], [first['context']['request_ref']])
        matches = second['repair_feedback']['source_value_matches']
        self.assertEqual(len(matches), 1)
        bindings = matches[0]['literal_matches_only']
        self.assertTrue(bindings)
        self.assertEqual({row['source_ref'] for row in bindings}, {quote['source_ref']})
        for row in bindings:
            self.assertEqual(row['relationship'], 'LITERAL_MATCH_ONLY')
            self.assertEqual(row['source_sha256'], quote['body_sha256'])
            self.assertEqual(quote['body'][row['start']:row['end']], '43')
        self.assertEqual(self.original_response(2)['steps'][0]['source_refs'],
                         [first['context']['request_ref']])

    def test_only_a_new_model_document_can_correct_the_citation(self):
        quote = self.source_model('correct-second')
        result = self.call()
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        self.assertEqual(result['model_calls'], 2)
        self.assertEqual(len(result['state']['verifications']), 1)
        first, second = self.original_response(1), self.original_response(2)
        self.assertEqual(first['steps'][0]['checks'], second['steps'][0]['checks'])
        self.assertNotEqual(first['steps'][0]['source_refs'], second['steps'][0]['source_refs'])
        self.assertEqual(second['steps'][0]['source_refs'], [quote['source_ref']])
        step = result['workflow']['plan']['steps'][0]
        self.assertEqual(step['spec']['checks'][0]['expected'], 43)
        self.assertEqual(step['expectation_origin'], 'MODEL_PROPOSED')
        self.assertEqual(step['independence'], 'NOT_ESTABLISHED')
        self.assertEqual(step['prose_entailment'], 'NOT_ASSESSED')
        self.assertFalse(result['authority_granted'])

    def test_hint_order_does_not_expand_or_mutate_source_choices(self):
        quote = self.source_model('wrong-request')
        self.call()
        initial, repair = self.sent(1), self.sent(2)
        before = deepcopy(repair)
        old = output_schema(initial)
        new = output_schema(repair)
        def refs(schema):
            return schema['properties']['steps']['items']['properties']['source_refs']['items']['enum']
        self.assertEqual(set(refs(old)), set(refs(new)))
        self.assertEqual(refs(new)[0], quote['source_ref'])
        self.assertEqual(repair, before)
        self.assertNotIn(initial['context']['selected_files'][0]['source_ref'], refs(new))
        old['properties']['steps']['items']['properties']['source_refs']['items']['enum'] = refs(new)
        self.assertEqual(old, new)

    def repair_resume(self, version):
        self.source_model('correct-second')
        write = InvocationJournal.write
        def old_feedback(journal, stage, value):
            if stage == 'started':
                if version is None:
                    value.pop('planning_repair_feedback', None)
                else:
                    value['planning_repair_feedback'] = version
            return write(journal, stage, value)
        def stop(stage):
            if stage == 'after_model_response' and self.counter.read_text() == '2':
                raise RuntimeError('Artificial interruption with second response saved')
        with mock.patch.object(InvocationJournal, 'write', new=old_feedback):
            with self.assertRaises(RuntimeError):
                self.call(fault=stop)
        saved = self.sent(2)
        if version is None:
            self.assertNotIn('repair_feedback', saved)
        else:
            self.assertIn('rejected_document', saved['repair_feedback'])
            self.assertNotIn('source_value_matches', saved['repair_feedback'])
        result = self.call()
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        self.assertEqual(self.counter.read_text(), '2')
        self.assertEqual(saved, self.sent(2))
        self.assertEqual(len(result['state']['verifications']), 1)
        self.assertFalse(result['authority_granted'])

    def test_old_v4_repair_without_feedback_resumes_unchanged(self):
        self.repair_resume(None)

    def test_old_v4_repair_feedback_one_resumes_without_new_diagnostics(self):
        self.repair_resume(1)


if __name__ == '__main__':
    unittest.main()
