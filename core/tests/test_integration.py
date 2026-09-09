"""Actual Git integration, stale authorization, conflicts and interrupted effects."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import os
import subprocess
import sys
import unittest

from test_constitution import Fixture, proposal, PRECEDENT
from verantyx.effects import authorize, execute
from verantyx.adoption import propose_adoption, authorize_adoption, adopt
from verantyx.integration import (plan_integration, resolve_integration, check_integration,
                                  authorize_integration, apply_integration, review_integration)
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore
from verantyx.kernel.reducer import replay, projection


@unittest.skipUnless(PRECEDENT, 'set VERANTYX_PRECEDENT')
class IntegrationTests(Fixture):
    def git(self, *args):
        return subprocess.run(['git','-C',str(self.root),'-c','core.hooksPath=/dev/null',*args],
                               check=True,capture_output=True).stdout.decode().strip()

    def prepare(self, mode='merge', diverge=None, dirty=False):
        self.init_git(); self.promote()
        self.run_task('candidate', proposal('candidate', action=True))
        lease = authorize(self.root,self.cfg,'candidate','writer',PRECEDENT,'lease',clock=self.clock)
        self.lease_id = lease['lease_id']
        execute(self.root,self.cfg,'candidate',lease['lease_id'],PRECEDENT,'execute',clock=self.clock)
        adopted = propose_adoption(self.root,self.cfg,'candidate',lease['lease_id'],PRECEDENT,'adoption',clock=self.clock)
        aid=adopted['adoption_id']
        authorize_adoption(self.root,self.cfg,'candidate',aid,PRECEDENT,'adoption-permit',reason='fixture',clock=self.clock)
        result=adopt(self.root,self.cfg,'candidate',aid,PRECEDENT,'adopt',clock=self.clock)
        self.adopted=result['adoption']['receipt']['commit']
        self.branch=self.git('symbolic-ref','HEAD')
        self.base=self.git('rev-parse','HEAD')
        if not dirty:
            (self.root/'calc.py').write_text(self.git('show','HEAD:calc.py')+'\n')
        if diverge:
            for p,s in diverge.items(): (self.root/p).write_text(s)
            self.git('add',*diverge)
            self.git('-c','user.name=Fixture','-c','user.email=fixture@invalid','commit','-qm','other work')
        self.before=self.git('rev-parse','HEAD')
        planned=plan_integration(self.root,self.cfg,'candidate',aid,PRECEDENT,'plan',branch=self.branch,mode=mode,clock=self.clock)
        self.identifier=planned['integration_id']
        return planned

    def verify(self):
        return check_integration(self.root,self.cfg,'candidate',self.identifier,PRECEDENT,'verify',clock=self.clock)

    def permit(self, ttl=300):
        return authorize_integration(self.root,self.cfg,'candidate',self.identifier,PRECEDENT,'permit',reason='fixture integration',ttl=ttl,clock=self.clock)

    def apply(self, **kwargs):
        return apply_integration(self.root,self.cfg,'candidate',self.identifier,PRECEDENT,'apply',clock=self.clock,**kwargs)

    def test_clean_checked_out_merge_requires_own_verification_and_permission(self):
        plan=self.prepare()
        self.assertEqual(plan['integration']['status'],'PLANNED')
        self.assertEqual(self.git('rev-parse','HEAD'),self.before)
        with self.assertRaises(LedgerError): self.apply()
        with self.assertRaises(LedgerError): self.permit()
        self.assertEqual(self.verify()['integration']['status'],'VERIFIED')
        self.permit(); result=self.apply()
        self.assertEqual(result['integration']['status'],'INTEGRATED', result)
        self.assertIn('return a + b',(self.root/'calc.py').read_text())
        self.assertEqual(self.git('show','-s','--format=%P','HEAD').split(),[self.before,self.adopted])
        self.assertEqual(self.git('diff','--name-only'), '')
        self.assertTrue(self.apply()['duplicate'])

    def test_rebase_single_adopted_change_preserves_divergent_commit(self):
        self.prepare(mode='rebase',diverge={'notes.txt':'a separate change\n'})
        self.verify(); self.permit(); result=self.apply()
        self.assertEqual(result['integration']['status'],'INTEGRATED')
        self.assertEqual(self.git('show','-s','--format=%P','HEAD'),self.before)
        self.assertEqual((self.root/'notes.txt').read_text(),'a separate change\n')
        self.assertIn('return a + b',(self.root/'calc.py').read_text())

    def test_conflict_needs_explicit_resolution_and_reverification(self):
        plan=self.prepare(diverge={'calc.py':'def add(a, b):\n    return a - b\n'})
        self.assertEqual(plan['integration']['status'],'CONFLICTED')
        with self.assertRaises(LedgerError): self.verify()
        resolved=resolve_integration(self.root,self.cfg,'candidate',self.identifier,PRECEDENT,'resolve',
              files={'calc.py':'def add(a, b):\n    return a + b\n'},reason='manual fixture resolution',clock=self.clock)
        self.assertEqual(resolved['integration']['status'],'PLANNED')
        with self.assertRaises(LedgerError): self.permit()
        self.verify(); self.permit(); self.assertEqual(self.apply()['integration']['status'],'INTEGRATED')

    def test_uncommitted_edits_prevent_canonical_permission(self):
        self.prepare(dirty=True)
        old=(self.root/'calc.py').read_bytes()
        self.verify()
        with self.assertRaises(LedgerError): self.permit()
        self.assertEqual((self.root/'calc.py').read_bytes(),old)
        self.assertEqual(self.git('rev-parse','HEAD'),self.before)

    def test_changed_candidate_rejected_after_permission(self):
        self.prepare(); self.verify(); self.permit()
        view=review_integration(self.root,self.cfg,'candidate',self.identifier)
        (Path(view['worktree'])/'calc.py').write_text('def add(a,b): return 5\n')
        result=self.apply()
        self.assertEqual(result['integration']['status'],'INVALIDATED')
        self.assertEqual(self.git('rev-parse','HEAD'),self.before)

    def test_expired_before_and_after_started_never_updates_ref(self):
        self.prepare(); self.verify(); self.permit(ttl=1)
        def fault(stage):
            if stage=='after_start': self.time+=timedelta(seconds=2)
        result=self.apply(fault=fault)
        self.assertEqual(result['integration']['status'],'OUTCOME_UNKNOWN')
        self.assertEqual(self.git('rev-parse','HEAD'),self.before)
        self.assertNotIn('a + b',(self.root/'calc.py').read_text())

    def test_interrupted_after_ref_is_recognized_without_reapplying(self):
        self.prepare(); self.verify(); self.permit()
        def fault(stage):
            if stage=='after_ref': raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.apply(fault=fault)
        commit=self.git('rev-parse','HEAD')
        with mock.patch('verantyx.integration._replace',side_effect=AssertionError('reapplied')):
            result=self.apply()
        self.assertEqual(result['integration']['status'],'INTEGRATED')
        self.assertTrue(result['integration']['receipt']['recovered'])
        self.assertEqual(self.git('rev-parse','HEAD'),commit)

    def test_partial_canonical_effect_becomes_unknown_without_reapply(self):
        self.prepare(); self.verify(); self.permit()
        def fault(stage):
            if stage=='after_files': raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.apply(fault=fault)
        with mock.patch('verantyx.integration._replace',side_effect=AssertionError('reapplied')):
            result=self.apply()
        self.assertEqual(result['integration']['status'],'OUTCOME_UNKNOWN')
        self.assertEqual(self.git('rev-parse','HEAD'),self.before)

    def test_frozen_tests_and_out_of_scope_resolution_cannot_be_replaced(self):
        self.prepare()
        for name in ('test_calc.py','new.py','../outside'):
            with self.assertRaises(LedgerError):
                resolve_integration(self.root,self.cfg,'candidate',self.identifier,PRECEDENT,'bad-'+name.replace('/','x'),
                                    files={name:'# replacement'},reason='fixture',clock=self.clock)

    def test_hooks_filters_and_merge_drivers_are_not_called(self):
        self.prepare()
        marker=self.root/'side-effect'
        hook=self.root/'.git/hooks/post-merge';hook.write_text('#!/bin/sh\ntouch '+repr(str(marker))+'\n');hook.chmod(0o755)
        self.git('config','filter.fixture.smudge','touch '+repr(str(marker)))
        self.verify(); self.permit(); result=self.apply()
        self.assertEqual(result['integration']['status'],'INTEGRATED')
        self.assertFalse(marker.exists())

    def test_replay_performs_no_live_git_io(self):
        self.prepare();self.verify();self.permit();self.apply()
        with EventStore(self.root,self.cfg['project']['id']) as store: events=store.events('candidate')
        expected=projection(replay(events))['projection_hash']
        with mock.patch('subprocess.run',side_effect=AssertionError('I/O')):
            self.assertEqual(projection(replay(events))['projection_hash'],expected)

    def test_change_after_file_install_is_not_reported_integrated(self):
        self.prepare(); self.verify(); self.permit()
        def mutate(stage):
            if stage == 'after_files':
                (self.root / 'calc.py').write_text('synthetic concurrent local edit\n')
        result = self.apply(fault=mutate)
        self.assertEqual(result['integration']['status'], 'OUTCOME_UNKNOWN')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.before)

    def test_change_after_ref_update_is_not_reported_integrated(self):
        self.prepare(); self.verify(); self.permit()
        def mutate(stage):
            if stage == 'after_ref':
                (self.root / 'calc.py').write_text('synthetic concurrent local edit\n')
        result = self.apply(fault=mutate)
        self.assertEqual(result['integration']['status'], 'OUTCOME_UNKNOWN')
        self.assertNotEqual(self.git('rev-parse', 'HEAD'), self.before)

    def test_directory_becomes_file_only_when_no_untracked_entries_are_lost(self):
        from verantyx import integration
        self.init_git()
        (self.root / 'calc.py').write_text(self.git('show', 'HEAD:calc.py') + '\n')
        directory = self.root / 'folder'
        directory.mkdir(); (directory / 'old.txt').write_text('old\n')
        self.git('add', 'folder/old.txt')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@invalid', 'commit', '-qm', 'directory fixture')
        executor = integration.PrecedentBackend(PRECEDENT)
        before = integration._files(executor, self.root, self.git('rev-parse', 'HEAD'))
        after = {k: v for k, v in before.items() if k != 'folder/old.txt'}
        after['folder'] = integration._blob(executor, self.root, b'new file\n', '100644')
        unrelated = directory / 'untracked.txt'; unrelated.write_text('keep me\n')
        with self.assertRaises(LedgerError):
            integration._replace(executor, self.root, self.root, before, after)
        self.assertEqual(unrelated.read_text(), 'keep me\n')
        unrelated.unlink()
        integration._replace(executor, self.root, self.root, before, after)
        self.assertEqual((self.root / 'folder').read_text(), 'new file\n')

    def test_symlinked_parent_of_new_file_cannot_redirect_write(self):
        from verantyx import integration
        self.init_git()
        (self.root / 'calc.py').write_text(self.git('show', 'HEAD:calc.py') + '\n')
        outside = self.root.parent / ('outside-' + self.root.name)
        outside.mkdir(); self.addCleanup(outside.rmdir)
        (self.root / 'redirect').symlink_to(outside, target_is_directory=True)
        executor = integration.PrecedentBackend(PRECEDENT)
        before = integration._files(executor, self.root, self.git('rev-parse', 'HEAD'))
        after = dict(before)
        after['redirect/new.txt'] = integration._blob(executor, self.root, b'new\n', '100644')
        with self.assertRaises((LedgerError, OSError)):
            integration._replace(executor, self.root, self.root, before, after)
        self.assertFalse((outside / 'new.txt').exists())

    def test_registered_live_writer_blocks_permission_and_late_application(self):
        from verantyx import writers
        self.prepare(); self.verify()
        cwd = self.root / '.verantyx/worktrees' / self.lease_id
        def start(ttl):
            process = subprocess.Popen([sys.executable, '-I', '-c', 'import sys;sys.stdin.buffer.read()'],
                                       cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(lambda: process.communicate(timeout=5) if process.poll() is None else None)
            record = writers.register(self.root, self.cfg, 'candidate', self.lease_id, pid=process.pid,
                                      responsible='synthetic writer', ttl=ttl, clock=self.clock)
            return process, record['writer']['id']
        process, writer_id = start(1)
        self.time += timedelta(seconds=2)
        with self.assertRaises(LedgerError) as refused:
            self.permit()
        self.assertEqual(refused.exception.code, 'WRITER_CONFLICT')
        process.communicate(timeout=5)
        writers.release(self.root, self.cfg, writer_id, clock=self.clock)
        self.permit()
        process, _ = start(300)
        result = self.apply()
        self.assertEqual(result['integration']['status'], 'INVALIDATED')
        self.assertEqual(result['integration']['reason'], 'WRITER_CONFLICT')
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.before)
        process.communicate(timeout=5)
