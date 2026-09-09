"""Real Ed25519 verification at the CLI gate; keys are artificial test fixtures."""
from argparse import Namespace
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from test_constitution import Fixture
from verantyx import authority, config
from verantyx.application import dispatch, now, record_run
from verantyx.cli import parse, main
from verantyx.domain.codec import canonical, digest
from verantyx.errors import LedgerError
from verantyx.security_journal import Journal
from verantyx.storage.sqlite import EventStore


class AuthorityTests(Fixture):
    def setUp(self):
        super().setUp()
        self.time = now()
        self.key = Ed25519PrivateKey.generate()  # Fixture only; the product never generates a key.
        self.public = self.root / 'operator.pem'
        self.write_public(self.key)

    def write_public(self, key):
        self.public.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    def make(self, argv, **kwargs):
        return authority.request(self.root, self.cfg, argv, clock=self.clock, **kwargs)

    def sign(self, request, key=None):
        return (key or self.key).sign(authority.signing_bytes(request))

    def execute(self, request, **kwargs):
        return authority.execute(self.root, self.cfg, request, self.sign(request), clock=self.clock, **kwargs)

    def enable(self):
        return self.execute(self.make(['authority-enable', '--public-key', str(self.public)]))

    def decision(self, **kwargs):
        return self.make(['decide', 'task', '--point', 'separation', '--choice', 'isolate', '--reason', '人工署名試験', '--key', 'signed-decision'], **kwargs)

    def assert_code(self, code, callback):
        with self.assertRaises(LedgerError) as error:
            callback()
        self.assertEqual(error.exception.code, code)

    def test_enrollment_requires_external_signature_and_command_executes_once(self):
        self.run_task('task')
        self.assert_code('AUTHORITY_REQUIRED', lambda: dispatch(self.root, self.cfg, Namespace(command='authority-enable', public_key=str(self.public)), 'ja'))
        result = self.enable()
        self.assertEqual(result['authorization'], 'SIGNATURE_VERIFIED')
        approval = self.decision()
        self.assertEqual(self.execute(approval)['operation_status'], 'RETURNED_OK')
        self.assert_code('AUTHORITY_USED', lambda: self.execute(approval))
        with EventStore(self.root, self.cfg['project']['id']) as store:
            decisions = [e for e in store.events() if e['type'] == 'HumanDecisionRecorded']
        self.assertEqual(len(decisions), 1)
        state = authority.state(self.root, self.cfg)
        self.assertEqual(state['commands'][approval['nonce']]['status'], 'RETURNED_OK')
        self.assertTrue(state['enabled'])

    def test_signature_tampering_and_attacker_key_are_rejected(self):
        self.enable()
        self.run_task('task')
        approval = self.decision()
        changed = deepcopy(approval)
        changed['operation']['arguments']['reason'] = 'forged'
        self.assert_code('AUTHORITY_SIGNATURE_INVALID', lambda: authority.execute(self.root, self.cfg, changed, self.sign(approval), clock=self.clock))
        attacker = Ed25519PrivateKey.generate()
        changed = deepcopy(approval)
        changed['operator_key'] = attacker.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        self.assert_code('AUTHORITY_KEY_INVALID', lambda: authority.execute(self.root, self.cfg, changed, self.sign(changed, attacker), clock=self.clock))
        self.assert_code('AUTHORITY_SIGNATURE_INVALID', lambda: authority.execute(self.root, self.cfg, approval, b'\x00' * 64, clock=self.clock))

    def test_project_revision_configuration_and_argument_types_are_bound(self):
        self.enable()
        self.run_task('task')
        approval = self.decision()
        record_run(self.root, self.cfg, run_id='task', resume=True, key='refresh', clock=self.clock)
        self.assert_code('AUTHORITY_STALE', lambda: self.execute(approval))
        approval = self.decision()
        changed = deepcopy(self.cfg)
        changed['learning']['mode'] = 'off'
        self.assert_code('AUTHORITY_STALE', lambda: authority.execute(self.root, changed, approval, self.sign(approval), clock=self.clock))
        malformed = deepcopy(approval)
        malformed['authority_revision'] = True
        self.assert_code('AUTHORITY_REQUEST_INVALID', lambda: authority.execute(self.root, self.cfg, malformed, self.sign(malformed), clock=self.clock))

    def test_bound_input_file_change_is_rejected(self):
        self.enable()
        self.run_task('task')
        answers = self.root / 'answers.json'
        answers.write_text('{}')
        approval = self.make(['learn-exercise-answer', 'task', '--candidate', 'one', '--exercise', 'fixed', '--key', 'answer', '--answers', str(answers)])
        answers.write_text('{"altered":true}')
        self.assert_code('AUTHORITY_INPUT_CHANGED', lambda: self.execute(approval))
        self.assertNotIn(approval['nonce'], authority.state(self.root, self.cfg)['commands'])

    def test_expiry_before_and_after_consumption_does_not_create_decision(self):
        self.enable()
        self.run_task('task')
        approval = self.decision(ttl=1)
        self.time += timedelta(seconds=2)
        self.assert_code('AUTHORITY_EXPIRED', lambda: self.execute(approval))
        approval = self.decision(ttl=1)
        def delay(stage):
            if stage == 'after_started':
                self.time += timedelta(seconds=2)
        self.assert_code('AUTHORITY_EXPIRED', lambda: self.execute(approval, fault=delay))
        self.assert_code('AUTHORITY_USED', lambda: self.execute(approval))
        with EventStore(self.root, self.cfg['project']['id']) as store:
            self.assertNotIn('HumanDecisionRecorded', [e['type'] for e in store.events()])

    def test_interruption_after_operation_keeps_unknown_receipt_and_never_retries(self):
        self.enable()
        self.run_task('task')
        approval = self.decision()
        def interrupt(stage):
            if stage == 'after_operation':
                raise RuntimeError('simulated interruption')
        with self.assertRaises(RuntimeError):
            self.execute(approval, fault=interrupt)
        self.assert_code('AUTHORITY_USED', lambda: self.execute(approval))
        status = authority.inspect(self.root, self.cfg, history=True)['commands'][-1]
        self.assertEqual(status['status'], 'INTERRUPTED_OR_RUNNING')
        self.assertIsNone(status['result_hash'])

    def test_rotation_changes_key_without_rewriting_history(self):
        self.enable()
        before = Journal(self.root, 'authority', self.cfg['project']['id']).read()
        replacement = Ed25519PrivateKey.generate()
        self.write_public(replacement)
        approval = self.make(['authority-rotate', '--public-key', str(self.public)])
        self.execute(approval)
        after = Journal(self.root, 'authority', self.cfg['project']['id']).read()
        self.assertEqual(after[:len(before)], before)
        self.run_task('task')
        request = self.decision()
        self.assert_code('AUTHORITY_SIGNATURE_INVALID', lambda: self.execute(request))
        self.key = replacement
        self.assertTrue(self.execute(request)['ok'])

    def test_unknown_commands_and_operator_bypasses_are_default_denied(self):
        self.enable()
        operations = ['decide', 'authorize', 'execute', 'adoption-authorize', 'adopt', 'rule-activate', 'rule-policy-accept',
                      'learn-target', 'learn-exercise-answer', 'memory-save', 'memory-start', 'propose', 'job-submit', 'worker',
                      'import', 'setup', 'tutorial', 'writer-register', 'writer-release', 'integration-apply', 'future-mutating-command']
        for command in operations:
            with self.subTest(command=command):
                self.assert_code('AUTHORITY_REQUIRED', lambda: dispatch(self.root, self.cfg, Namespace(command=command), 'ja'))
        self.assert_code('AUTHORITY_REQUIRED', lambda: dispatch(self.root, self.cfg, Namespace(command='export', output=str(self.root/'export')), 'ja'))

    def test_unsigned_candidate_intake_does_not_create_grants_or_human_decisions(self):
        self.enable()
        _, args = parse(['run', 'candidate only', '--task-id', 'candidate', '--key', 'candidate'])
        result = dispatch(self.root, self.cfg, args, 'ja')
        self.assertTrue(result['ok'])
        with EventStore(self.root, self.cfg['project']['id']) as store:
            self.assertFalse(set(e['type'] for e in store.events()) & {'HumanDecisionRecorded', 'EffectAuthorized', 'RuleActivated'})
        self.assertTrue(dispatch(self.root, self.cfg, Namespace(command='authority-status'), 'ja')['enabled'])

    def test_replay_verifies_stored_signature_without_live_clock_or_process(self):
        self.enable()
        entries = Journal(self.root, 'authority', self.cfg['project']['id']).read()
        expected = authority.state(self.root, self.cfg)
        with mock.patch('verantyx.application.now', side_effect=AssertionError('clock')), mock.patch('subprocess.run', side_effect=AssertionError('process')):
            self.assertEqual(authority.replay(entries), expected)
        forged = deepcopy(entries)
        forged[0]['payload']['signature'] = 'AA=='
        self.assert_code('AUTHORITY_SIGNATURE_INVALID', lambda: authority.replay(forged))

    def test_cli_request_sign_execute_and_concurrent_replay(self):
        self.run_task('task')
        self.enable()
        invocation = self.root / 'invocation.json'
        invocation.write_text(json.dumps({'argv': self.decision()['operation']['argv']}))
        approval_file = self.root / 'approval.json'
        signature_file = self.root / 'approval.sig'
        cmd = [sys.executable, '-m', 'verantyx', '--project', str(self.root), '--json']
        prepared = subprocess.run([*cmd, 'authority-request', '--invocation', str(invocation), '--output', str(approval_file)], text=True, capture_output=True)
        self.assertEqual(prepared.returncode, 0, prepared.stderr + prepared.stdout)
        approval = json.loads(approval_file.read_bytes())
        self.assertEqual(approval_file.read_bytes(), authority.signing_bytes(approval))
        signature_file.write_bytes(self.sign(approval))
        argv = [*cmd, 'authority-execute', '--approval', str(approval_file), '--signature', str(signature_file)]
        workers = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        outputs = [worker.communicate(timeout=30) for worker in workers]
        values = [json.loads(out) for out, err in outputs]
        self.assertEqual(sum(bool(value['ok']) for value in values), 1, outputs)
        rejection = next(value for value in values if not value['ok'])
        self.assertIn(rejection['error']['code'], ('AUTHORITY_USED', 'STORE_BUSY'))

    def test_cli_setup_and_tutorial_cannot_reset_enabled_policy(self):
        self.enable()
        for argv in (['setup', '--non-interactive', '--name', 'different'],):
            with self.subTest(argv=argv):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = main(['--project', str(self.root), '--json', *argv])
                self.assertNotEqual(code, 0)
                self.assertEqual(json.loads(output.getvalue())['error']['code'], 'AUTHORITY_REQUIRED')
        self.assertTrue(authority.state(self.root, self.cfg)['enabled'])

    def test_expiry_during_last_input_revalidation_never_dispatches(self):
        self.enable()
        self.run_task('task')
        approval = self.decision(ttl=1)
        original = authority._input_files
        calls = 0
        def advance(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(*args, **kwargs)
            if calls == 2:
                self.time += timedelta(seconds=2)
            return result
        with mock.patch.object(authority, '_input_files', side_effect=advance), mock.patch('verantyx.application.dispatch', return_value={'ok': True}) as dispatch:
            with self.assertRaises(LedgerError) as error:
                self.execute(approval)
            self.assertEqual(error.exception.code, 'AUTHORITY_EXPIRED')
            dispatch.assert_not_called()

    def test_expired_started_timestamp_cannot_corrupt_future_authority_replay(self):
        self.enable()
        self.run_task('task')
        approval = self.decision(ttl=1)
        calls = 0
        def advancing_clock():
            nonlocal calls
            calls += 1
            return self.time + (timedelta(seconds=2) if calls >= 2 else timedelta())
        with self.assertRaises(LedgerError) as error:
            authority.execute(self.root, self.cfg, approval, self.sign(approval), clock=advancing_clock)
        self.assertEqual(error.exception.code, 'AUTHORITY_EXPIRED')
        self.assertTrue(authority.state(self.root, self.cfg)['enabled'])

    def test_configuration_file_change_after_consumption_rejects_dispatch(self):
        self.enable()
        self.run_task('task')
        approval = self.decision()
        def change(stage):
            if stage == 'after_started':
                existing, raw = config.load(self.root)
                changed = deepcopy(existing)
                changed['learning']['mode'] = 'off'
                config.save(self.root, changed, raw)
        with mock.patch('verantyx.application.dispatch', return_value={'ok': True}) as dispatch:
            with self.assertRaises(LedgerError) as error:
                self.execute(approval, fault=change)
            self.assertEqual(error.exception.code, 'AUTHORITY_STALE')
            dispatch.assert_not_called()

    def queued_signed_job(self):
        from verantyx import jobs
        from verantyx.adapters.invocation_journal import InvocationJournal
        result = self.run_task('task')
        script = self.root / 'proposal_adapter.py'
        script.write_text("import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps(x['proposal_template']))\n")
        adapter = self.root / 'adapter.json'
        adapter.write_text(json.dumps({'argv': [sys.executable, str(script)]}))
        args = ['job-submit', 'task', '--adapter', str(adapter), '--key', 'bound-job',
                '--expected-revision', str(result['recorded_revision'])]
        original = jobs.submit
        def submit_and_attest(*positional, **keywords):
            result = original(*positional, **keywords)
            with InvocationJournal(self.root, 'job', 'bound-job') as journal:
                authority.attest_proposal_job(self.root, self.cfg, journal, journal.read('queued'))
            return result
        with mock.patch.object(jobs, 'submit', side_effect=submit_and_attest):
            self.execute(self.make(args))
        journal = InvocationJournal(self.root, 'job', 'bound-job')
        return journal, journal.read('queued')

    def test_signed_job_attestation_is_bound_and_malicious_sidecar_is_rejected(self):
        self.enable()
        journal, job = self.queued_signed_job()
        permitted = authority.require_proposal_job_approval(self.root, self.cfg, journal, job)
        self.assertEqual(permitted['mode'], 'SIGNED_PROPOSAL_JOB')
        stage = 'operator-approval-' + permitted['source_nonce']
        marker = journal.read(stage)
        marker['job_hash'] = '0' * 64
        journal.path(stage).write_text(canonical(marker))
        self.assert_code('AUTHORITY_JOB_MISMATCH', lambda: authority.require_proposal_job_approval(self.root, self.cfg, journal, job))

    def test_signed_job_changes_and_old_operator_keys_are_rejected(self):
        self.enable()
        journal, job = self.queued_signed_job()
        changed = deepcopy(job)
        changed['adapter_sha256'] = '0' * 64
        self.assert_code('AUTHORITY_JOB_MISMATCH', lambda: authority.require_proposal_job_approval(self.root, self.cfg, journal, changed))
        replacement = Ed25519PrivateKey.generate()
        self.write_public(replacement)
        self.execute(self.make(['authority-rotate', '--public-key', str(self.public)]))
        self.assert_code('AUTHORITY_JOB_MISMATCH', lambda: authority.require_proposal_job_approval(self.root, self.cfg, journal, job))

    def test_unsigned_job_cannot_gain_attestation_when_protection_is_enabled(self):
        from verantyx import jobs
        from verantyx.adapters.invocation_journal import InvocationJournal
        self.enable()
        result = self.run_task('task')
        adapter = self.root / 'unsigned-adapter.json'
        adapter.write_text(json.dumps({'argv': [sys.executable, '-c', 'print(1)']}))
        # Bypass the CLI only to construct the untrusted fixture. The gate normally rejects this call.
        try:
            jobs.submit(self.root, self.cfg, 'task', adapter_path=adapter, key='unsigned', expected_revision=result['recorded_revision'])
        except LedgerError as error:
            self.assertEqual(error.code, 'AUTHORITY_REQUIRED')
        journal = InvocationJournal(self.root, 'job', 'unsigned')
        job = journal.read('queued')
        self.assertIsNotNone(job)
        self.assert_code('AUTHORITY_REQUIRED', lambda: authority.attest_proposal_job(self.root, self.cfg, journal, job))
        self.assert_code('AUTHORITY_JOB_MISMATCH', lambda: authority.require_proposal_job_approval(self.root, self.cfg, journal, job))

    def test_job_attestation_replay_does_not_read_home_files_or_clock(self):
        self.enable()
        self.queued_signed_job()
        entries = Journal(self.root, 'authority', self.cfg['project']['id']).read()
        expected = authority.replay(entries)
        with mock.patch('pathlib.Path.expanduser', side_effect=AssertionError('HOME dependency')), mock.patch('subprocess.run', side_effect=AssertionError('process')):
            self.assertEqual(authority.replay(entries), expected)

    def test_effect_boundary_helper_rejects_exact_expiry_before_second_effect(self):
        self.enable()
        self.run_task('task')
        approval = self.decision(ttl=1)
        effects = []
        def two_effects(*args, **kwargs):
            self.assertEqual(authority.require_current_approval_valid(), approval['expires_at'])
            effects.append('first')
            self.time += timedelta(seconds=1)
            authority.require_current_approval_valid()
            effects.append('second')
            return {'ok': True}
        with mock.patch('verantyx.application.dispatch', side_effect=two_effects):
            self.assert_code('AUTHORITY_EXPIRED', lambda: self.execute(approval))
        self.assertEqual(effects, ['first'])
        self.assert_code('AUTHORITY_USED', lambda: self.execute(approval))

    def test_effect_boundary_helper_rejects_clock_before_issued_at(self):
        self.enable()
        self.run_task('task')
        approval = self.decision()
        def clock_reversed(*args, **kwargs):
            self.time -= timedelta(seconds=1)
            authority.require_current_approval_valid()
            return {'ok': True}
        with mock.patch('verantyx.application.dispatch', side_effect=clock_reversed):
            self.assert_code('AUTHORITY_EXPIRED', lambda: self.execute(approval))

    def test_effect_boundary_helper_keeps_absent_context_path_unchanged(self):
        with mock.patch('verantyx.application.now', side_effect=AssertionError('no active signature')):
            self.assertIsNone(authority.require_current_approval_valid())
