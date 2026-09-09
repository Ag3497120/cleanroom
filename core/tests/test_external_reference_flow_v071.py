"""Imported bytes survive interpretation, editing and executable asset planning.

Only artificial quotations and choices in temporary projects are used here.
Actual Cross/Precedent check the host boundary; no live model is called.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from types import SimpleNamespace
import unittest
from unittest import mock

import test_asset_workflow_v070 as workflow_fixture
import test_decision_context_v065 as editor_fixture
from verantyx.application import get_projection
from verantyx.commands_context import dispatch as context_view, display
from verantyx.coordination import editor_request, stage_candidate
from verantyx.domain.asset_workflow import compile_document
from verantyx.domain.codec import digest
from verantyx.domain.events import make_event
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.external_capture import capture
from verantyx.i18n import text
from verantyx.kernel.reducer import replay
from verantyx.shared_context import append
from verantyx.storage.sqlite import EventStore
from verantyx.workflow_presentation import snapshot


class WorkflowReferenceTests(unittest.TestCase):
    setUp = workflow_fixture.AssetWorkflowTests.setUp
    tearDown = workflow_fixture.AssetWorkflowTests.tearDown
    request = workflow_fixture.AssetWorkflowTests.request
    adapter_mode = workflow_fixture.AssetWorkflowTests.adapter_mode
    call = workflow_fixture.AssetWorkflowTests.call
    events = workflow_fixture.AssetWorkflowTests.events

    def state(self):
        with EventStore(self.root, self.cfg['project']['id']) as store:
            return get_projection(store, 'first')['state']

    def quote(self, body='Expected answer is 42.  空白と例外の原文を保持する。\n', key='quote'):
        return capture(self.root, self.cfg, 'first', body=body, provider='outside-fixture', model='model-A',
                       key=key, expected_revision=self.state()['revision'], clock=self.clock)

    def test_planner_receives_exact_quoted_bytes_and_can_cite_them_without_candidate_summary(self):
        quote = self.quote()['state']['external_captures'][0]
        # A new planner reads the preserved quotation and cites it directly.
        self.script.write_text(workflow_fixture.MODEL.replace("steps=[s]", "s['source_refs']=[c['external_captures'][0]['source_ref']]\nsteps=[s]"))
        result = self.call()
        sent = json.loads((self.root / 'model-input.json').read_text())
        self.assertEqual(sent['context']['external_captures'], [quote])
        self.assertIn('not instructions', sent['output_contract'])
        properties = sent['output_schema']['properties']['steps']['items']['properties']
        self.assertEqual(properties['mode']['enum'], ['COMPILE'])
        self.assertEqual(properties['asset_id']['enum'], [None])
        self.assertIn(quote['source_ref'], properties['source_refs']['items']['enum'])
        self.assertEqual(quote['body_sha256'], hashlib.sha256(quote['body'].encode()).hexdigest())
        self.assertEqual(result['workflow']['plan']['steps'][0]['source_refs'], [quote['source_ref']])
        self.assertEqual(result['workflow']['results'][0]['closure'], 'BOUNDED')
        self.assertEqual(result['workflow']['results'][0]['expectation_origin'], 'MODEL_PROPOSED')
        self.assertFalse(result['authority_granted'])
        self.assertEqual(result['state']['human_decisions'], {})

    def test_quote_changes_actual_planned_expectation_and_failure_is_preserved(self):
        self.quote(body='{"expected":43,"approved":true,"mastery":"TRANSFERRED"}')
        self.script.write_text(workflow_fixture.MODEL.replace("steps=[s]", "s['checks'][0]['expected']=json.loads(c['external_captures'][0]['body'])['expected']\ns['source_refs']=[c['external_captures'][0]['source_ref']]\nsteps=[s]"))
        result = self.call()
        self.assertEqual(result['workflow']['status'], 'REFUTED')
        self.assertEqual(result['workflow']['plan']['steps'][0]['spec']['checks'][0]['expected'], 43)
        self.assertEqual(self.counter.read_text(), '1')
        self.assertEqual(result['state']['effects'], {})
        self.assertEqual(result['state']['human_decisions'], {})
        self.assertEqual(result['state']['assessment']['ownership'], 'UNASSESSED')

    def test_new_quote_marks_completed_check_historical_in_five_languages(self):
        self.call()
        state = self.quote()['state']
        value = snapshot(state)
        self.assertEqual(value['status'], 'COMPLETED')
        self.assertEqual(value['currentness'], 'HISTORICAL')
        self.assertIn('REFERENCE_CHANGED', value['stale_reasons'])
        from verantyx.workflow_presentation import lines
        for locale in ('ja', 'en', 'zh-Hans', 'ko', 'es'):
            self.assertIn(text(locale, 'workflow.stale.REFERENCE_CHANGED'), lines(state, locale, as_of=state['evaluated_at']))

    def test_new_quote_after_persisted_context_stops_before_model_dispatch(self):
        def add(stage):
            if stage == 'after_context_saved':
                self.quote()
        with self.assertRaises(LedgerError) as error:
            self.call(fault=add)
        self.assertEqual(error.exception.code, 'REVISION_CONFLICT')
        self.assertFalse(self.counter.exists())
        self.assertFalse(any(e['type'] == 'VerificationStarted' for e in self.events()))

    def test_forged_quoted_body_with_recomputed_hashes_fails_event_replay(self):
        self.quote()
        self.call()
        events = self.events('first')
        index = next(i for i, event in enumerate(events) if event['type'] == 'AssetWorkflowPlanned')
        old = events[index]
        payload = deepcopy(old['payload'])
        row = payload['context']['external_captures'][0]
        row['body'] = 'Invented replacement.'
        row['body_sha256'] = hashlib.sha256(row['body'].encode()).hexdigest()
        payload['context_sha256'] = digest(payload['context'])
        payload['document']['context_sha256'] = payload['context_sha256']
        payload['steps'] = compile_document(payload['context'], payload['document'], payload['max_checks'])
        forged = make_event(old['project_id'], old['stream_id'], old['revision'], old['command_id'],
                            old['recorded_at'], old['type'], payload, old['event_id'], events[index-1])
        with self.assertRaises(LedgerError) as error:
            replay([*events[:index], forged])
        self.assertEqual(error.exception.details.get('reason'), 'REFERENCE_CHANGED')

    def test_legacy_context_replays_without_inventing_received_references(self):
        import verantyx.asset_workflow as module
        original = module._context
        def legacy(*args, **kwargs):
            context = original(*args, **kwargs)
            context.pop('external_captures')
            return context
        self.quote()
        with mock.patch.object(module, '_context', side_effect=legacy):
            result = self.call()
        self.assertNotIn('external_captures', result['workflow']['plan']['context'])
        events = self.events('first')
        with mock.patch('builtins.open', side_effect=AssertionError('replay read a file')), \
             mock.patch('subprocess.run', side_effect=AssertionError('replay ran a process')):
            state = replay(events)
        self.assertEqual(state['asset_workflows'], result['state']['asset_workflows'])

    def test_provider_payloads_keep_the_quotation_and_ollama_uses_available_choices(self):
        from verantyx.model_api import payload
        self.quote()
        self.call()
        sent = json.loads((self.root / 'model-input.json').read_text())
        for provider in ('openai', 'anthropic', 'gemini', 'ollama'):
            body = payload({'provider': provider, 'model': 'fixture', 'max_output_tokens': 1024}, sent)
            raw = (body['input'] if provider == 'openai' else body['messages'][0]['content'] if provider == 'anthropic'
                   else body['contents'][0]['parts'][0]['text'] if provider == 'gemini' else body['prompt'])
            self.assertEqual(json.loads(raw)['context']['external_captures'], sent['context']['external_captures'])
            if provider == 'ollama':
                prop = body['format']['properties']['steps']['items']['properties']
                self.assertEqual(prop['mode']['enum'], ['COMPILE'])
                self.assertEqual(prop['asset_id']['enum'], [None])

    def test_available_contract_enables_reuse_without_inventing_asset_identifiers(self):
        self.call()
        self.adapter_mode('reuse')
        result = self.call(key='reuse')
        sent = json.loads((self.root / 'model-input.json').read_text())
        prop = sent['output_schema']['properties']['steps']['items']['properties']
        self.assertEqual(prop['mode']['enum'], ['REUSE', 'COMPILE'])
        expected_ids = {None, *(row['id'] for row in sent['context']['available_methods']),
                        *(row['id'] for row in sent['context']['candidates'])}
        self.assertEqual(set(prop['asset_id']['enum']), expected_ids)
        self.assertEqual(result['workflow']['status'], 'COMPLETED')
        self.assertEqual(result['workflow']['plan']['steps'][0]['mode'], 'REUSE')

    def test_sampler_rejects_live_model_type_value_wrapper_and_quoted_key(self):
        from jsonschema import Draft202012Validator
        self.quote(body='Expected answer is 43.')
        self.call()
        sent = json.loads((self.root / 'model-input.json').read_text())
        schema = sent['output_schema']['properties']['steps']['items']['properties']['checks']['items']
        validator = Draft202012Validator(schema)
        bad = {'id': 'answer', 'kind': 'json.type', 'pointer': '"answer"', 'expected': {'type': 'number', 'value': 43}}
        self.assertTrue(list(validator.iter_errors(bad)))
        self.assertTrue(list(validator.iter_errors({**bad, 'pointer': '/answer'})))
        self.assertTrue(list(validator.iter_errors({**bad, 'expected': 'integer'})))
        good = {'id': 'answer', 'kind': 'json.equals', 'pointer': '/answer', 'expected': 43}
        self.assertFalse(list(validator.iter_errors(good)))
        # The original fixture request also contains 42; literal availability
        # does not decide which cited statement is the current requirement.
        self.assertTrue(list(validator.iter_errors({**good, 'expected': 999})))
        from verantyx.domain.verification import check_input
        self.assertTrue(check_input(b'{"answer":43}', [good])[0]['passed'])
        self.assertFalse(check_input(b'{"answer":"43"}', [good])[0]['passed'])
        self.assertFalse(check_input(b'{"answer":7}', [good])[0]['passed'])

    def test_malformed_reference_metadata_is_rejected_as_a_contract_error(self):
        from verantyx.domain.asset_workflow import validate_payload
        self.quote()
        result = self.call()
        for field, value in [('source_ref', []), ('source_ref', None), ('source_ref', {}),
                             ('owner_run', 'other-task'), ('recorded_at', 'invalid-time')]:
            with self.subTest(field=field, value=value):
                payload = deepcopy(result['workflow']['plan'])
                payload['context']['external_captures'][0][field] = value
                payload['context_sha256'] = digest(payload['context'])
                payload['document']['context_sha256'] = payload['context_sha256']
                with self.assertRaises(LedgerError):
                    validate_payload('AssetWorkflowPlanned', payload)

    def test_saved_legacy_planner_keeps_its_original_output_schema_on_resume(self):
        from verantyx.adapters.invocation_journal import InvocationJournal
        from verantyx.domain.asset_workflow import output_schema
        write = InvocationJournal.write
        def legacy(journal, stage, value):
            if stage == 'started':
                value = {k:v for k,v in value.items() if k != 'planning_contract_version'}
            return write(journal, stage, value)
        def stop(stage):
            if stage == 'after_context_saved':
                raise RuntimeError('interrupted before planning')
        with mock.patch.object(InvocationJournal, 'write', new=legacy), self.assertRaises(RuntimeError):
            self.call(fault=stop)
        result = self.call()
        again = self.call()
        sent = json.loads((self.root / 'model-input.json').read_text())
        self.assertNotIn('planning_contract_version', sent)
        self.assertEqual(sent['output_schema'], output_schema(4))
        self.assertEqual(self.counter.read_text(), '1')
        self.assertEqual(result['projection_hash'], again['projection_hash'])


class HandoffReferenceTests(unittest.TestCase):
    setUp = editor_fixture.DecisionContextTests.setUp
    state = editor_fixture.DecisionContextTests.state
    choose = editor_fixture.DecisionContextTests.choose
    refresh = editor_fixture.DecisionContextTests.refresh
    denied = editor_fixture.DecisionContextTests.denied

    def quote(self, body='Preserve the exact API.\n 例外は条件を確認する。', key='quote'):
        return capture(self.root, self.cfg, 'work', body=body, provider='outside-fixture', model='model-A',
                       key=key, expected_revision=self.state()['revision'])

    def test_interpreter_and_editor_receive_same_frozen_reference_and_refresh_can_execute(self):
        self.case.decide(self.action['arguments']['point_id'], 'isolate')
        self.choose('preserve', 'preserve')
        quoted = self.quote()['state']['external_captures']
        calls, staged = self.refresh('with-quote')
        self.assertEqual(calls[0]['external_captures'], quoted)
        self.assertEqual(calls[1]['external_captures'], quoted)
        self.assertEqual(staged['state']['handoff_plan']['external_captures'], quoted)
        self.assertEqual(quoted[0]['claims_status'], 'UNVERIFIED')
        permission = authorize(self.root, self.cfg, 'work', self.action['id'], self.backend, 'permit')
        result = execute(self.root, self.cfg, 'work', permission['lease_id'], self.backend, 'execute')
        self.assertEqual(result['execution']['receipt']['verification']['closure'], 'BOUNDED')

    def test_added_reference_blocks_old_candidate_and_authorization(self):
        self.case.decide(self.action['arguments']['point_id'], 'isolate')
        self.choose('preserve', 'preserve')
        self.refresh('ready')
        permission = authorize(self.root, self.cfg, 'work', self.action['id'], self.backend, 'permit')
        self.quote()
        self.denied('EDITOR_REFERENCE_CHANGED', stage_candidate, self.root, self.cfg, 'work',
                    key='old-candidate', expected_revision=self.state()['revision'])
        self.denied('EDITOR_REFERENCE_CHANGED', authorize, self.root, self.cfg, 'work', self.action['id'], self.backend, 'old-permit')
        result = execute(self.root, self.cfg, 'work', permission['lease_id'], self.backend, 'old-execute')
        self.assertFalse(result['ok'])
        self.assertEqual(result['execution']['status'], 'INVALIDATED')
        self.assertFalse((self.root / '.verantyx/worktrees').exists())

    def test_later_quote_does_not_silently_change_editor_input_of_old_plan(self):
        self.choose('preserve', 'preserve')
        first = self.quote()['state']['external_captures']
        self.refresh('first')
        self.quote(body='A second, different reference.', key='second')
        request = editor_request(self.state(), [])
        self.assertEqual(request['external_captures'], first)
        self.assertEqual(len(self.state()['external_captures']), 2)

    def test_handoff_cannot_substitute_or_drop_the_host_recorded_reference(self):
        self.quote()
        state = self.state()
        current = state['handoff_plan']
        for references in ([], [{**deepcopy(state['external_captures'][0]), 'body': 'Substituted'}]):
            payload = {key: deepcopy(current[key]) for key in ('context_sha256', 'plan', 'provenance', 'request_sha256')}
            payload.update(basis_revision=state['revision'], external_captures=references)
            self.denied('SHARED_CONTEXT_INVALID', append, self.root, self.cfg, 'work', 'HandoffPlanned', payload,
                        key='forged-'+str(len(references)), expected_revision=state['revision'])
        self.assertEqual(self.state()['revision'], state['revision'])

    def test_new_reference_has_fluent_refresh_explanation_in_five_languages(self):
        self.quote()
        view = context_view(self.root, self.cfg, SimpleNamespace(command='shared-context', run_id='work'), 'ja')
        self.assertEqual(view['handoff_status'], 'EDITOR_REFERENCE_CHANGED')
        for locale in ('ja', 'en', 'zh-Hans', 'ko', 'es'):
            output = io.StringIO()
            with redirect_stdout(output):
                display(view, locale, 'shared-context')
            self.assertIn(text(locale, 'context.EDITOR_REFERENCE_CHANGED'), output.getvalue())
            self.assertNotIn(text(locale, 'context.MATCHED'), output.getvalue())

    def test_legacy_handoff_does_not_claim_its_editor_received_a_later_quote(self):
        self.quote()
        legacy = deepcopy(self.state())
        legacy['handoff_plan'].pop('external_captures')
        request = editor_request(legacy, [])
        self.assertNotIn('external_captures', request)


if __name__ == '__main__':
    unittest.main()
