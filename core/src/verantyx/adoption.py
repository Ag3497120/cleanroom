"""Adopt a verified immutable candidate into an explicitly selected Git branch.

Ref updates are compare-and-swap. Checked-out branches are refused; working files
and the operator's index are never overwritten. No merge hooks or filters run.
"""
from datetime import timedelta
from pathlib import Path
import difflib
import hashlib
import os
import subprocess
import tempfile
import uuid

from .adapters.observations import read_document, normalize_path
from .adapters.precedent_backend import PrecedentBackend
from .adapters.proposal_validation import valid_id
from .application import now, iso, _receipt_view
from .domain.codec import digest
from .domain.adoption import verified_effect
from .domain.events import make_event
from .effects import _gate
from .errors import LedgerError
from .kernel.reducer import replay
from .storage.sqlite import EventStore


def _git(executor, root, *arguments, data=None, extra_env=None, missing=False):
    # Reuse the executor's trust/environment checks before binary plumbing.
    executor.git(root, "rev-parse", "--git-dir")
    env = dict(os.environ)
    env.update(extra_env or {})
    result = subprocess.run(["git", "-C", str(root), "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                             *arguments], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30)
    if missing and result.returncode == 1:
        return None
    if result.returncode or len(result.stdout) > 17 * 1024 * 1024:
        raise LedgerError("ADOPTION_GIT_FAILED")
    return result.stdout


def _head(executor, root, ref):
    value = _git(executor, root, "rev-parse", "--verify", "--quiet", ref + "^{commit}", missing=True)
    return value.decode().strip() if value else None


def _target(executor, root, branch):
    ref = branch if branch.startswith("refs/heads/") else "refs/heads/" + branch
    _git(executor, root, "check-ref-format", ref)
    checkouts = executor.git(root, "worktree", "list", "--porcelain").splitlines()
    if "branch " + ref in checkouts:
        raise LedgerError("ADOPTION_BRANCH_CHECKED_OUT")
    return ref, _head(executor, root, ref)


def _base_files(executor, root, base):
    result = {}
    for row in filter(None, executor.git(root, "ls-tree", "-rz", "--full-tree", base).split("\0")):
        meta, name = row.split("\t", 1)
        mode, kind, oid = meta.split()
        normalize_path(name)
        if kind != "blob" or mode not in ("100644", "100755"):
            raise LedgerError("SOURCE_UNSAFE")
        result[name] = (mode, oid)
    return result


def _candidate(executor, root, effect):
    lease = effect["lease"]
    target = Path(root).resolve() / ".verantyx/worktrees" / lease["id"]
    if Path(effect["receipt"]["worktree"]) != target or target.is_symlink() or not target.is_dir():
        raise LedgerError("ADOPTION_CANDIDATE_CHANGED")
    actual = executor.snapshot(target)
    if actual["base_version"] != lease["base_version"]:
        raise LedgerError("ADOPTION_CANDIDATE_CHANGED")
    expected, base = {}, _base_files(executor, root, lease["base_version"])
    patch = lease["plan"]["files"]
    for name in sorted(set(base) | set(patch)):
        if name in patch:
            raw = patch[name].encode("utf-8")
        else:
            raw = _git(executor, root, "cat-file", "blob", base[name][1])
        expected[name] = {"status": "OBSERVED", "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        # New files may be ignored by Git; they still belong to the tested patch.
        try:
            current = read_document(target / name, 16 * 1024 * 1024)
            executable = bool((target / name).stat().st_mode & 0o111)
        except (OSError, LedgerError):
            raise LedgerError("ADOPTION_CANDIDATE_CHANGED") from None
        if hashlib.sha256(current).hexdigest() != expected[name]["sha256"]:
            raise LedgerError("ADOPTION_CANDIDATE_CHANGED")
        mode = base.get(name, ("100644", None))[0]
        if executable != (mode == "100755"):
            raise LedgerError("ADOPTION_CANDIDATE_CHANGED")
    # Detect changes outside the proposal as well as changes to the tested files.
    for name, item in actual["files"].items():
        if expected.get(name) != item:
            raise LedgerError("ADOPTION_CANDIDATE_CHANGED")
    if set(base) - set(actual["files"]):
        raise LedgerError("ADOPTION_CANDIDATE_CHANGED")
    return digest({"files": expected, "base_version": lease["base_version"], "index_hash": actual["index_hash"]})


def _effect(state, lease_id):
    effect = state["effects"].get(lease_id)
    if not verified_effect(effect):
        raise LedgerError("ADOPTION_NOT_VERIFIED")
    if digest(state["proposal"]) != effect["lease"]["proposal_hash"]:
        raise LedgerError("ADOPTION_STALE")
    return effect


def _read(store, run_id):
    events = store.events(run_id)
    if not events:
        raise LedgerError("RUN_NOT_FOUND")
    return events, replay(events)


def _append(store, previous, events, key, intent, clock):
    batch, command_id = [], str(uuid.uuid4())
    for kind, payload in [*events, ("EvaluationRecorded", {"as_of": iso(clock()), "evaluator": "m1.v1"})]:
        batch.append(make_event(store.project_id, previous[-1]["stream_id"], previous[-1]["revision"] + len(batch) + 1,
                                command_id, iso(clock()), kind, payload, str(uuid.uuid4()), batch[-1] if batch else previous[-1]))
    return store.append(key, digest(intent), previous[-1]["stream_id"], previous[-1]["revision"], batch)


def _view(receipt, key):
    result = _receipt_view(receipt, key)
    for event in receipt["events"]:
        if event["command_id"] == receipt["command_id"] and event["type"].startswith("Adoption"):
            payload = event["payload"]
            identifier = payload["plan"]["id"] if event["type"] == "AdoptionProposed" else payload["adoption_id"]
            result["adoption_id"] = identifier
            result["adoption"] = result["state"]["adoptions"][identifier]
    result["ok"] = result.get("adoption", {}).get("status") not in ("INVALIDATED", "OUTCOME_UNKNOWN")
    return result


def _check(store, root, state, plan, precedent_path, clock, backend):
    effect = _effect(state, plan["effect_lease_id"])
    executor = PrecedentBackend(precedent_path, expected_hash=plan["backend_hash"])
    context = _gate(store, state, effect["lease"]["plan"], clock, backend)
    ref, before = _target(executor, root, plan["target_ref"])
    if before != plan["target_before"] or digest(executor.snapshot(root)) != plan["source_hash"]:
        raise LedgerError("ADOPTION_STALE")
    if _candidate(executor, root, effect) != plan["candidate_hash"]:
        raise LedgerError("ADOPTION_CANDIDATE_CHANGED")
    return executor, context, effect


def _check_authority(item, context, clock):
    if iso(clock()) >= item["authorization"]["expires_at"]:
        raise LedgerError("LEASE_EXPIRED")
    if digest(context["rules"]) != item["authorization"]["rule_context_hash"]:
        raise LedgerError("RULE_CHANGED")


def propose_adoption(root, configuration, run_id, lease_id, precedent_path, key, *, branch="verantyx/canonical",
                     message="Adopt verified Vera candidate", clock=now, backend=None):
    if not valid_id(key) or type(message) is not str or not 1 <= len(message.strip()) <= 2000:
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "adoption-propose", "run_id": run_id, "lease_id": lease_id, "branch": branch,
              "message": message, "precedent": str(Path(precedent_path).resolve())}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        effect = _effect(state, lease_id)
        executor = PrecedentBackend(precedent_path, expected_hash=effect["lease"]["backend_hash"])
        source = executor.snapshot(root)
        ref, before = _target(executor, root, branch)
        if source["base_version"] != effect["lease"]["base_version"] or before not in (None, source["base_version"]):
            raise LedgerError("ADOPTION_STALE")
        _gate(store, state, effect["lease"]["plan"], clock, backend)
        plan = {"id": str(uuid.uuid4()), "effect_lease_id": lease_id, "execution_ref": effect["receipt_ref"],
                "proposal_hash": effect["lease"]["proposal_hash"], "base_version": source["base_version"],
                "target_ref": ref, "target_before": before, "source_hash": digest(source),
                "candidate_hash": _candidate(executor, root, effect), "backend_hash": executor.fingerprint,
                "backend_identity": executor.identity, "files": effect["receipt"]["applied"],
                "tests": effect["lease"]["plan"]["tests"], "message": message}
        return _view(_append(store, previous, [("AdoptionProposed", {"plan": plan})], key, intent, clock), key)


def authorize_adoption(root, configuration, run_id, adoption_id, precedent_path, key, *, reason,
                       ttl=300, clock=now, backend=None):
    if not valid_id(key) or type(ttl) is not int or not 1 <= ttl <= 3600 or not reason or not reason.strip():
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "adoption-authorize", "run_id": run_id, "adoption_id": adoption_id,
              "ttl": ttl, "reason": reason, "precedent": str(Path(precedent_path).resolve())}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get("adoptions", {}).get(adoption_id)
        if not item or item["status"] != "PROPOSED":
            raise LedgerError("ADOPTION_STAGE")
        _, context, _ = _check(store, root, state, item["plan"], precedent_path, clock, backend)
        payload = {"adoption_id": adoption_id, "plan_hash": digest(item["plan"]), "basis_revision": state["revision"],
                   "expires_at": iso(clock() + timedelta(seconds=ttl)), "rule_context_hash": digest(context["rules"]), "reason": reason}
        return _view(_append(store, previous, [("PolicyContextRecorded", context), ("AdoptionAuthorized", payload)],
                             key, intent, clock), key)


def _commit(executor, root, effect, plan, recorded_at):
    base = _base_files(executor, root, plan["base_version"])
    # A disposable index avoids altering the user's staging area or invoking filters.
    with tempfile.TemporaryDirectory(prefix="adoption-", dir=Path(root) / ".verantyx") as directory:
        env = {"GIT_INDEX_FILE": str(Path(directory) / "index"), "GIT_AUTHOR_NAME": "Verantyx",
               "GIT_AUTHOR_EMAIL": "verantyx@localhost", "GIT_COMMITTER_NAME": "Verantyx",
               "GIT_COMMITTER_EMAIL": "verantyx@localhost", "GIT_AUTHOR_DATE": recorded_at, "GIT_COMMITTER_DATE": recorded_at}
        _git(executor, root, "read-tree", plan["base_version"], extra_env=env)
        for name, content in effect["lease"]["plan"]["files"].items():
            oid = _git(executor, root, "hash-object", "-w", "--stdin", data=content.encode(), extra_env=env).decode().strip()
            mode = base.get(name, ("100644", None))[0]
            _git(executor, root, "update-index", "--add", "--cacheinfo", mode + "," + oid + "," + name, extra_env=env)
        tree = _git(executor, root, "write-tree", extra_env=env).decode().strip()
        return _git(executor, root, "-c", "commit.gpgSign=false", "commit-tree", tree, "-p", plan["base_version"],
                    data=(plan["message"] + "\n\nVera-Adoption: " + plan["id"] + "\n").encode(), extra_env=env).decode().strip()


def adopt(root, configuration, run_id, adoption_id, precedent_path, key, *, clock=now, backend=None, fault=None):
    if not valid_id(key):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "adopt", "run_id": run_id, "adoption_id": adoption_id, "precedent": str(Path(precedent_path).resolve())}
    with EventStore(root, configuration["project"]["id"], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached:
            return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get("adoptions", {}).get(adoption_id)
        if not item or item["status"] not in ("AUTHORIZED", "STARTED"):
            raise LedgerError("ADOPTION_STAGE")
        plan, recovered, error = item["plan"], item["status"] == "STARTED", None
        if recovered:
            commit = item["commit"]
            try:
                executor = PrecedentBackend(precedent_path, expected_hash=plan["backend_hash"])
                if _head(executor, root, plan["target_ref"]) != commit:
                    error = "INTERRUPTED_ADOPTION"
            except (LedgerError, OSError, subprocess.SubprocessError):
                error = "INTERRUPTED_ADOPTION"
        else:
            try:
                if iso(clock()) >= item["authorization"]["expires_at"]:
                    raise LedgerError("LEASE_EXPIRED")
                executor, context, effect = _check(store, root, state, plan, precedent_path, clock, backend)
                _check_authority(item, context, clock)
                commit = _commit(executor, root, effect, plan, iso(clock()))
                # Commit construction may take longer than the remaining lease.
                _check_authority(item, context, clock)
            except LedgerError as problem:
                return _view(_append(store, previous, [("AdoptionInvalidated", {"adoption_id": adoption_id, "reason": problem.code})],
                                     key, intent, clock), key)
            started = _append(store, previous, [("PolicyContextRecorded", context),
                                                ("AdoptionStarted", {"adoption_id": adoption_id, "commit": commit})],
                              "adoption-start-" + adoption_id, {"adoption_start": adoption_id}, clock)
            previous = started["events"]
            if fault:
                fault("after_start")
            try:
                # Recheck after preparing the commit; update-ref supplies the atomic ref precondition.
                _, context, _ = _check(store, root, replay(previous), plan, precedent_path, clock, backend)
                _check_authority(item, context, clock)
                _git(executor, root, "update-ref", "--no-deref", "-m", "Vera authorized adoption", plan["target_ref"],
                     commit, plan["target_before"] or "0" * len(commit))
            except (LedgerError, OSError, subprocess.SubprocessError) as problem:
                error = getattr(problem, "code", "ADOPTION_GIT_FAILED")
            if fault:
                fault("after_ref")
        payload = {"adoption_id": adoption_id, "outcome": "OUTCOME_UNKNOWN" if error else "ADOPTED",
                   "target_ref": plan["target_ref"], "base_version": plan["base_version"], "commit": commit,
                   "execution_ref": plan["execution_ref"], "recovered": recovered, "reason": error}
        return _view(_append(store, previous, [("AdoptionReceipt", payload)], key, intent, clock), key)


def review_adoption(root, configuration, run_id, adoption_id, precedent_path):
    with EventStore(root, configuration["project"]["id"]) as store:
        _, state = _read(store, run_id)
        item = state.get("adoptions", {}).get(adoption_id)
        if not item:
            raise LedgerError("ADOPTION_STAGE")
        effect = state["effects"][item["plan"]["effect_lease_id"]]
        executor = PrecedentBackend(precedent_path, expected_hash=item["plan"]["backend_hash"])
        base = _base_files(executor, root, item["plan"]["base_version"])
        changes = []
        for name, content in effect["lease"]["plan"]["files"].items():
            before = _git(executor, root, "cat-file", "blob", base[name][1]).decode("utf-8", "replace") if name in base else ""
            diff = "".join(difflib.unified_diff(before.splitlines(True), content.splitlines(True), fromfile="a/" + name, tofile="b/" + name))
            changes.append({"path": name, "sha256": item["plan"]["files"][name], "diff": diff[:30000], "diff_truncated": len(diff) > 30000})
        return {"schema_version": 1, "ok": True, "adoption_id": adoption_id, "adoption": item,
                "changes": changes, "verification": effect["receipt"]["verification"],
                "working_files_modified": False, "review_is_historical": True}
