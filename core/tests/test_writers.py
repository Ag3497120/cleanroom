"""Real child process registrations with exclusive candidate destinations."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import os
import subprocess
import sys
import unittest

from test_constitution import Fixture, PRECEDENT, proposal
from verantyx import writers
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.domain.codec import digest
from verantyx.security_journal import Journal


@unittest.skipUnless(PRECEDENT, 'set VERANTYX_PRECEDENT for actual integration')
class WriterTests(Fixture):
    def setUp(self):
        super().setUp()
        self.children = []
        self.init_git()
        self.promote()
        self.run_task('candidate', proposal('candidate', action=True))
        permitted = authorize(self.root, self.cfg, 'candidate', 'writer', PRECEDENT, 'permit', clock=self.clock)
        self.lease_id = permitted['lease_id']
        result = execute(self.root, self.cfg, 'candidate', self.lease_id, PRECEDENT, 'execute', clock=self.clock)
        self.assertTrue(result['ok'], result.get('execution'))
        self.workspace = Path(result['execution']['receipt']['worktree'])

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.terminate()
            child.wait(timeout=10)
            if child.stdin:
                child.stdin.close()
            if child.stdout:
                child.stdout.close()
        super().tearDown()

    def child(self, cwd=None):
        child = subprocess.Popen([sys.executable, '-u', '-c', "import sys,time; print('ready',flush=True); sys.stdin.read()"],
                                 cwd=cwd or self.workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.children.append(child)
        self.assertEqual(child.stdout.readline().strip(), 'ready')
        return child

    def register(self, child, **kwargs):
        return writers.register(self.root, self.cfg, 'candidate', self.lease_id, pid=child.pid, responsible='人工writer責任者', clock=self.clock, **kwargs)['writer']

    def assert_code(self, code, callback):
        with self.assertRaises(LedgerError) as error:
            callback()
        self.assertEqual(error.exception.code, code)

    def test_gateway_records_real_pid_and_releases_only_its_completed_writer(self):
        recorded = writers.inspect(self.root, self.cfg)['writers']
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0]['process']['pid'], os.getpid())
        self.assertEqual(recorded[0]['status'], 'RELEASED')
        self.assertEqual(recorded[0]['release_reason'], 'GATEWAY_COMPLETED')

    def test_two_live_processes_cannot_share_target_even_after_lease_expiry(self):
        first, second = self.child(), self.child()
        writer = self.register(first, ttl=1)
        self.assert_code('WRITER_CONFLICT', lambda: self.register(second))
        self.time += timedelta(seconds=2)
        observation = writers.observe(self.root, self.cfg, writer['id'], clock=self.clock)['observations'][0]
        self.assertEqual(observation['status'], 'LEASE_EXPIRED_LIVE')
        self.assert_code('WRITER_CONFLICT', lambda: self.register(second))
        self.assert_code('WRITER_STILL_RUNNING', lambda: writers.release(self.root, self.cfg, writer['id'], clock=self.clock))
        self.assert_code('WRITER_CONFLICT', lambda: writers.assert_no_live_writers(self.root, self.cfg, self.root, clock=self.clock))
        self.assertIsNone(first.poll())
        self.assertIsNone(second.poll())

    def test_dead_writer_is_observed_and_replacement_never_signals_other_process(self):
        first, second = self.child(), self.child()
        writer = self.register(first)
        first.terminate()
        first.wait(timeout=10)
        result = writers.release(self.root, self.cfg, writer['id'], clock=self.clock)
        self.assertEqual(result['reason'], 'DEAD')
        self.assertFalse(result['process_signalled'])
        self.assertEqual(self.register(second)['process']['pid'], second.pid)
        self.assertIsNone(second.poll())

    def test_reused_pid_observation_does_not_follow_or_signal_new_process(self):
        child = self.child()
        writer = self.register(child)
        # Real process runs; inject only a different start identity to model OS PID reuse.
        reused = writers.process_identity(child.pid)
        reused['start_id'] += ':different-birth'
        with mock.patch.object(writers, 'process_identity', return_value=reused), mock.patch('os.kill', side_effect=AssertionError('must not signal')):
            result = writers.release(self.root, self.cfg, writer['id'], clock=self.clock)
        self.assertEqual(result['reason'], 'PID_REUSED')
        self.assertIsNone(child.poll())

    def test_wrong_cwd_and_nonexistent_pid_do_not_register_canonical_writer(self):
        child = self.child(self.root)
        self.assert_code('WRITER_WORKSPACE_INVALID', lambda: self.register(child))
        child.terminate()
        child.wait(timeout=10)
        self.assert_code('WRITER_PROCESS_INVALID', lambda: self.register(child))
        self.assertEqual(len(writers.inspect(self.root, self.cfg)['writers']), 1)

    def test_renewal_binds_original_process_and_only_extends_live_lease(self):
        child = self.child()
        writer = self.register(child, ttl=10)
        self.time += timedelta(seconds=1)
        result = writers.renew(self.root, self.cfg, writer['id'], ttl=20, clock=self.clock)
        self.assertGreater(result['expires_at'], writer['expires_at'])
        self.time += timedelta(seconds=21)
        self.assert_code('WRITER_PROCESS_INVALID', lambda: writers.renew(self.root, self.cfg, writer['id'], ttl=100, clock=self.clock))

    def test_recorded_replay_never_reads_live_process_or_clock(self):
        writer = self.register(self.child())
        writers.observe(self.root, self.cfg, writer['id'], clock=self.clock)
        entries = Journal(self.root, 'writers', self.cfg['project']['id']).read()
        expected = writers.replay(entries)
        with mock.patch.object(writers, 'process_identity', side_effect=AssertionError('process')), mock.patch('verantyx.application.now', side_effect=AssertionError('clock')):
            self.assertEqual(writers.replay(entries), expected)
        forged = deepcopy(entries)
        forged[-1]['payload']['observation']['status'] = 'DEAD'
        self.assert_code('SECURITY_INTEGRITY', lambda: writers.replay(forged))

    def test_symlink_destination_and_fabricated_effect_lease_are_rejected(self):
        child = self.child()
        self.assert_code('LEASE_NOT_FOUND', lambda: writers.register(self.root, self.cfg, 'candidate', '00000000-0000-0000-0000-000000000000', pid=child.pid, responsible='fixture'))
        renamed = self.workspace.with_name('moved')
        self.workspace.rename(renamed)
        self.workspace.symlink_to(renamed, target_is_directory=True)
        self.assert_code('WRITER_WORKSPACE_INVALID', lambda: self.register(child))

    def test_renewal_replay_rejects_changed_cwd_identity(self):
        child = self.child()
        writer = self.register(child, ttl=10)
        self.time += timedelta(seconds=1)
        writers.renew(self.root, self.cfg, writer['id'], ttl=20, clock=self.clock)
        entries = Journal(self.root, 'writers', self.cfg['project']['id']).read()
        entries[-1]['payload']['process']['cwd'] = str(self.root)
        entries[-1]['hash'] = digest({k: v for k, v in entries[-1].items() if k != 'hash'})
        with self.assertRaises(LedgerError) as error:
            writers.replay(entries)
        self.assertEqual(error.exception.code, 'SECURITY_INTEGRITY')

    def test_external_registration_replay_rejects_mismatched_workspace(self):
        self.register(self.child())
        entries = Journal(self.root, 'writers', self.cfg['project']['id']).read()
        entries[-1]['payload']['process']['cwd'] = str(self.root)
        entries[-1]['hash'] = digest({k: v for k, v in entries[-1].items() if k != 'hash'})
        with self.assertRaises(LedgerError) as error:
            writers.replay(entries)
        self.assertEqual(error.exception.code, 'SECURITY_INTEGRITY')

    def test_boot_wall_clock_changes_do_not_reidentify_a_live_process(self):
        child = self.child()
        with mock.patch('psutil.boot_time', side_effect=[1.0, 99999.0]):
            first = writers.process_identity(child.pid)
            second = writers.process_identity(child.pid)
        self.assertEqual(first['status'], 'ALIVE')
        self.assertEqual(first['start_id'], second['start_id'])
