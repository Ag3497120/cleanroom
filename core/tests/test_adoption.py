"""Actual Git adoption, stale authority, negative controls and crash recovery."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest import mock
import subprocess
import shlex
import tempfile
import unittest

from test_constitution import Fixture, proposal, PRECEDENT
from verantyx.adoption import propose_adoption, authorize_adoption, adopt, review_adoption
from verantyx import adoption as adoption_module, config
from verantyx.application import get_projection, iso
from verantyx.domain.events import make_event
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay, projection
from verantyx.storage.sqlite import EventStore


@unittest.skipUnless(PRECEDENT, "set VERANTYX_PRECEDENT for actual integration")
class AdoptionTests(Fixture):
    def candidate(self, bad=False, files=None):
        self.init_git()
        self.promote()
        document = proposal("candidate", action=True)
        if bad:
            document["actions"][0]["arguments"]["files"]["calc.py"] = "def add(a, b):\n    return 5\n"
        document["actions"][0]["arguments"]["files"].update(files or {})
        self.run_task("candidate", document)
        lease = authorize(self.root, self.cfg, "candidate", "writer", PRECEDENT, "exec-lease", clock=self.clock)
        result = execute(self.root, self.cfg, "candidate", lease["lease_id"], PRECEDENT, "execute", clock=self.clock)
        self.effect_id = lease["lease_id"]
        self.candidate_path = Path(result["execution"]["receipt"]["worktree"])
        return result

    def propose(self, **kwargs):
        return propose_adoption(self.root, self.cfg, "candidate", self.effect_id, PRECEDENT, "propose", clock=self.clock, **kwargs)

    def permit(self, identifier, **kwargs):
        return authorize_adoption(self.root, self.cfg, "candidate", identifier, PRECEDENT, "permit", reason="人工試験の採用判断",
                                  clock=self.clock, **kwargs)

    def commit(self, identifier, **kwargs):
        return adopt(self.root, self.cfg, "candidate", identifier, PRECEDENT, "adopt", clock=self.clock, **kwargs)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, check=True).stdout

    def test_adoption_creates_real_commit_preserves_source_and_has_separate_permission(self):
        self.candidate()
        source = (self.root / "calc.py").read_bytes()
        index = self.git("ls-files", "--stage", "-z")
        base = self.git("rev-parse", "HEAD").decode().strip()
        plan = self.propose()
        identifier = plan["adoption_id"]
        with self.assertRaises(LedgerError) as error:
            self.commit(identifier)
        self.assertEqual(error.exception.code, "ADOPTION_STAGE")
        review = review_adoption(self.root, self.cfg, "candidate", identifier, PRECEDENT)
        self.assertIn("+    return a + b", review["changes"][0]["diff"])
        self.permit(identifier)
        result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "ADOPTED", result["adoption"])
        commit = result["adoption"]["receipt"]["commit"]
        self.assertEqual(self.git("rev-parse", "verantyx/canonical").decode().strip(), commit)
        self.assertEqual(self.git("show", "verantyx/canonical:calc.py"), b"def add(a, b):\n    return a + b\n")
        self.assertEqual(self.git("rev-parse", commit + "^1").decode().strip(), base)
        self.assertEqual((self.root / "calc.py").read_bytes(), source)
        self.assertEqual(self.git("ls-files", "--stage", "-z"), index)
        self.assertTrue(self.commit(identifier)["duplicate"])

    def test_failing_candidate_cannot_enter_adoption(self):
        self.candidate(bad=True)
        with self.assertRaises(LedgerError) as error:
            self.propose()
        self.assertEqual(error.exception.code, "ADOPTION_NOT_VERIFIED")

    def test_checked_out_branch_cannot_be_forced(self):
        self.candidate()
        branch = self.git("symbolic-ref", "HEAD").decode().strip()
        with self.assertRaises(LedgerError) as error:
            self.propose(branch=branch)
        self.assertEqual(error.exception.code, "ADOPTION_BRANCH_CHECKED_OUT")

    def test_changed_test_or_candidate_rejected(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        (self.candidate_path / "test_calc.py").write_text("# tests were replaced after verification\n")
        result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "INVALIDATED")
        self.assertEqual(result["adoption"]["reason"], "ADOPTION_CANDIDATE_CHANGED")

    def test_expiration_invalidates_adoption(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier, ttl=1)
        self.time += timedelta(seconds=2)
        self.assertEqual(self.commit(identifier)["adoption"]["reason"], "LEASE_EXPIRED")

    def test_expiration_during_commit_preparation_does_not_update_ref(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier, ttl=1)
        original = adoption_module._commit
        def delayed_commit(*args):
            commit = original(*args)
            self.time += timedelta(seconds=2)
            return commit
        with mock.patch.object(adoption_module, "_commit", side_effect=delayed_commit):
            result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "INVALIDATED")
        self.assertEqual(result["adoption"]["reason"], "LEASE_EXPIRED")
        self.assertEqual(self.git("for-each-ref", "--format=%(refname)", "refs/heads/verantyx/canonical"), b"")

    def test_expiration_after_start_does_not_update_ref(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier, ttl=1)
        def delay(stage):
            if stage == "after_start":
                self.time += timedelta(seconds=2)
        result = self.commit(identifier, fault=delay)
        self.assertEqual(result["adoption"]["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(result["adoption"]["receipt"]["reason"], "LEASE_EXPIRED")
        self.assertEqual(self.git("for-each-ref", "--format=%(refname)", "refs/heads/verantyx/canonical"), b"")

    def test_deleted_candidate_is_recorded_as_invalidated(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        (self.candidate_path / "calc.py").unlink()
        result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "INVALIDATED")
        self.assertEqual(result["adoption"]["reason"], "ADOPTION_CANDIDATE_CHANGED")
        self.assertTrue(self.commit(identifier)["duplicate"])

    def test_rule_withdrawal_invalidates_adoption(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            rule = next(event["payload"]["rule_id"] for event in store.events() if event["type"] == "RuleActivated")
        self.command("rule-retire", rule, reason="採用直前に撤回")
        result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "INVALIDATED")
        self.assertEqual(result["adoption"]["reason"], "EXECUTION_BLOCKED")

    def test_ref_change_does_not_overwrite_other_commit(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        self.git("branch", "verantyx/canonical", "HEAD")
        result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "INVALIDATED")
        self.assertEqual(self.git("rev-parse", "verantyx/canonical"), self.git("rev-parse", "HEAD"))

    def test_ref_competitor_between_check_and_update_is_not_overwritten(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        competing = self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@invalid",
                             "commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "competing change").decode().strip()
        original = adoption_module._git
        def concurrent_update(executor, root, *args, **kwargs):
            if args[0] == "update-ref":
                self.git("update-ref", "refs/heads/verantyx/canonical", competing)
            return original(executor, root, *args, **kwargs)
        with mock.patch.object(adoption_module, "_git", side_effect=concurrent_update):
            result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "OUTCOME_UNKNOWN")
        self.assertEqual(self.git("rev-parse", "verantyx/canonical").decode().strip(), competing)

    def test_replay_rejects_mismatched_verification_and_authority(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        self.commit(identifier)
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("candidate")
        mutations = {
            "different_test_scope": ("ExecutionReceipt", lambda payload: payload["verification"]["scope"].update(tests=[])),
            "different_rule_context": ("AdoptionAuthorized", lambda payload: payload.update(rule_context_hash="0" * 64)),
            "already_expired_authority": ("AdoptionAuthorized", lambda payload: payload.update(expires_at=iso(self.time - timedelta(seconds=1)))),
            "started_after_expiry": ("AdoptionStarted", None),
        }
        for label, (kind, mutate) in mutations.items():
            with self.subTest(label=label):
                changed = []
                for event in events:
                    payload = deepcopy(event["payload"])
                    recorded_at = event["recorded_at"]
                    if event["type"] == kind:
                        if mutate:
                            mutate(payload)
                        else:
                            recorded_at = iso(self.time + timedelta(seconds=300))
                    changed.append(make_event(event["project_id"], event["stream_id"], event["revision"], event["command_id"],
                                              recorded_at, event["type"], payload, event["event_id"], changed[-1] if changed else None))
                with self.assertRaises(LedgerError) as error:
                    replay(changed)
                self.assertEqual(error.exception.code, "STORE_INTEGRITY")

    def test_custom_branch_and_new_file_do_not_run_hooks_or_filters(self):
        self.candidate(files={"nested/追加.py": "LABEL = '保存された候補'\n"})
        self.git("branch", "release/review", "HEAD")
        hook_marker = self.root / ".git/hook-invoked"
        filter_marker = self.root / ".git/filter-invoked"
        hook = self.root / ".git/hooks/reference-transaction"
        hook.write_text("#!/bin/sh\nprintf invoked > " + shlex.quote(str(hook_marker)) + "\n")
        hook.chmod(0o755)
        (self.root / ".git/info/attributes").write_text("*.py filter=tripwire\n")
        self.git("config", "filter.tripwire.clean", "touch " + shlex.quote(str(filter_marker)) + "; cat")
        self.git("config", "filter.tripwire.smudge", "touch " + shlex.quote(str(filter_marker)) + "; cat")
        identifier = self.propose(branch="release/review")["adoption_id"]
        self.permit(identifier)
        result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "ADOPTED")
        self.assertEqual(result["adoption"]["receipt"]["target_ref"], "refs/heads/release/review")
        self.assertEqual(self.git("show", "release/review:nested/追加.py"), "LABEL = '保存された候補'\n".encode())
        self.assertFalse((self.root / "nested/追加.py").exists())
        self.assertFalse(hook_marker.exists())
        self.assertFalse(filter_marker.exists())

    def test_archive_preserves_adoption_citations_without_local_authority(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        adopted = self.commit(identifier)["adoption"]
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            raw = store.export().encode()
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory).resolve()
            cfg = config.defaults(other, "ja")
            config.save(other, cfg, None)
            with EventStore(other, cfg["project"]["id"], create=True) as store:
                imported = store.import_archive(raw, iso(self.clock()))
                view = get_projection(store, "candidate", imported["archive_id"])
                self.assertEqual(view["state"]["adoptions"][identifier], adopted)
                self.assertEqual(view["state"]["trust"], "ARCHIVE_ONLY")
                self.assertFalse(view["state"]["can_execute_effects"])
                self.assertEqual(store.export(imported["archive_id"]).encode(), raw)
                self.assertEqual(store.runs(), [])
            with self.assertRaises(LedgerError) as error:
                adopt(other, cfg, "candidate", identifier, PRECEDENT, "imported-adoption", clock=self.clock)
            self.assertEqual(error.exception.code, "RUN_NOT_FOUND")

    def test_crash_after_atomic_ref_update_reconciles_without_repeating(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        def interrupt(stage):
            if stage == "after_ref":
                raise RuntimeError("simulated lost response")
        with self.assertRaises(RuntimeError):
            self.commit(identifier, fault=interrupt)
        before = self.git("rev-parse", "verantyx/canonical")
        result = self.commit(identifier)
        self.assertEqual(result["adoption"]["status"], "ADOPTED")
        self.assertTrue(result["adoption"]["receipt"]["recovered"])
        self.assertEqual(self.git("rev-parse", "verantyx/canonical"), before)

    def test_crash_before_ref_update_stays_unknown_and_replay_is_pure(self):
        self.candidate()
        identifier = self.propose()["adoption_id"]
        self.permit(identifier)
        def interrupt(stage):
            if stage == "after_start":
                raise RuntimeError("simulated process loss")
        with self.assertRaises(RuntimeError):
            self.commit(identifier, fault=interrupt)
        self.assertEqual(self.commit(identifier)["adoption"]["status"], "OUTCOME_UNKNOWN")
        with EventStore(self.root, self.cfg["project"]["id"]) as store:
            events = store.events("candidate")
        expected = projection(replay(events))
        with mock.patch("subprocess.run", side_effect=AssertionError("process during replay")), \
             mock.patch("time.time", side_effect=AssertionError("clock during replay")):
            self.assertEqual(projection(replay(events)), expected)
