"""Source-retaining repair and bounded input regressions, with artificial models."""
from copy import deepcopy
import unittest
from unittest import mock

import test_shared_context
from verantyx.application import record_run
from verantyx.coordination import _invoke
from verantyx.coordination_schema import source_units
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.storage.sqlite import EventStore


class HandoffBottlenecksTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_shared_context.SharedContextTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.cfg = self.fixture.root, self.fixture.cfg

    def test_incorrect_interpreter_reconsiders_source_instead_of_forcing_editor(self):
        result = self.fixture.workflow(
            "d['acknowledgements'][-1]['disposition']='DEFERRED'",
            "d['interpretations'][-1]['disposition']='DEFERRED' if v.get('repair_feedback') else 'FORBIDDEN'")
        state = result['state']
        self.assertEqual(len(state['handoff_plans']), 2)
        self.assertEqual(len(state['editor_attempts']), 2)
        first, second = state['handoff_plans']
        self.assertEqual(first['plan']['interpretations'][-1]['disposition'], 'FORBIDDEN')
        self.assertEqual(second['plan']['interpretations'][-1]['disposition'], 'DEFERRED')
        self.assertEqual(second['reconsideration']['editor_ref'], state['editor_attempts'][0]['source_ref'])
        self.assertEqual(state['editor_attempt']['validation']['status'], 'MATCHED')
        self.assertEqual(state['editor_attempt']['validation']['semantic_fidelity'], 'UNPROVEN')
        self.assertEqual(state['effects'], {})
        calls = self.fixture.fixture.invocations()
        plans = [c for c in calls if c['format'] == 'verantyx.handoff-plan-request.v1']
        self.assertEqual(plans[0]['shared_context'], plans[1]['shared_context'])
        self.assertIn('previous_plan', plans[1]['repair_feedback'])
        self.assertEqual(plans[1]['selected_files'][1]['path'], 'test_calc.py')
        with EventStore(self.root, self.cfg['project']['id']) as store:
            events = store.events('work')
        with mock.patch('subprocess.run', side_effect=AssertionError('replay executed')):
            self.assertEqual(replay(events)['editor_attempt'], state['editor_attempt'])

    def test_correct_interpreter_does_not_need_to_accept_incorrect_editor(self):
        result = self.fixture.workflow("if not v['repair_feedback']: d['acknowledgements'][-1]['disposition']='FORBIDDEN'")
        plans = result['state']['handoff_plans']
        self.assertEqual(len(plans), 2)
        self.assertTrue(all(p['plan']['interpretations'][-1]['disposition'] == 'DEFERRED' for p in plans))
        self.assertEqual(result['state']['editor_attempt']['validation']['status'], 'MATCHED')

    def test_no_repair_budget_does_not_add_an_unrequested_reconsideration(self):
        result = self.fixture.workflow("d['acknowledgements'][-1]['disposition']='FORBIDDEN'", max_repairs=0)
        self.assertEqual(len(result['state']['handoff_plans']), 1)
        self.assertEqual(result['state']['editor_attempt']['validation']['status'], 'REPAIR_REQUIRED')

    def test_64_65_and_many_spans_preserve_every_byte_and_final_condition(self):
        for count in (64, 65, 300):
            original = '\n\n ' + ''.join('条件' + str(i) + '。' for i in range(1, count + 1)) + '\n  '
            request = {'shared_context': {'sources': [{'id': 'original', 'text': original}]}}
            units = source_units(request)
            self.assertEqual(len(units), min(count, 64))
            self.assertEqual(''.join(u['quote'] for u in units), original)
            self.assertIn('条件' + str(count) + '。', units[-1]['quote'])
            self.assertTrue(all(u['quote'] in original for u in units))

    def test_grouping_never_mixes_sources_or_loses_short_sources(self):
        sources = [{'id': 'long', 'text': '条件。' * 65}, {'id': 'short', 'text': '最後の制約。'}]
        units = source_units({'shared_context': {'sources': sources}})
        self.assertEqual(len(units), 64)
        for source in sources:
            self.assertEqual(''.join(u['quote'] for u in units if u['source_id'] == source['id']), source['text'])

    def test_65_span_handoff_reaches_cross_with_all_original_conditions(self):
        from verantyx.responses import ask
        mutation = (
            "d['interpretations']=[dict(u,meaning=u['quote'],disposition='NOW',strength='MUST',alternatives=[]) for u in v['source_units']]; "
            "d['relations']=[]; d['cases'][0]['interpretation_ids']=[n['id'] for n in d['interpretations']]")
        proposer, editor = self.fixture.adapters(planner_mutation=mutation)
        original = ''.join('条件' + str(i) + '。' for i in range(1, 66))
        result = ask(self.root, self.cfg, request=original, adapter_path=proposer, editor_adapter=editor,
                     include_paths=['calc.py', 'test_calc.py'], key='long', run_id='long', max_repairs=0)
        state = result['state']
        self.assertEqual(state['editor_attempt']['validation']['status'], 'MATCHED')
        self.assertEqual(state['editor_attempt']['validation']['mode'], 'CROSS_VM')
        self.assertEqual(''.join(n['quote'] for n in state['handoff_plan']['plan']['interpretations']), original)
        self.assertEqual(state['shared_context']['sources'][0]['text'], original)
        self.assertEqual(state['effects'], {})

    def _invoke_with_concurrent_append(self, change_current):
        state = self.fixture.workflow()['state']
        def response(_):
            if change_current:
                record_run(self.root, self.cfg, run_id='work', resume=True, key='concurrent')
            else:
                record_run(self.root, self.cfg, run_id='other', request='Unrelated task', key='concurrent')
            return '{}'
        with mock.patch('verantyx.adapters.command_process.BoundedProcess') as process:
            process.return_value.__enter__.return_value.document.side_effect = response
            return _invoke(self.root, self.cfg, 'work', self.root / 'vera.json', {'format': 'fixture'},
                           key='concurrent-generation', revision=state['revision'], timeout=60,
                           validate=lambda value: value, role='VERA_INTERPRETER')

    def test_unrelated_task_append_does_not_discard_frozen_generation(self):
        document, _ = self._invoke_with_concurrent_append(False)
        self.assertEqual(document, {})

    def test_changed_current_task_still_discards_generation(self):
        with self.assertRaises(LedgerError) as error:
            self._invoke_with_concurrent_append(True)
        self.assertEqual(error.exception.code, 'REVISION_CONFLICT')


if __name__ == '__main__':
    unittest.main()
