"""Three-way file integration in a candidate worktree, then separate canonical permission."""
from datetime import timedelta
from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import stat
import subprocess
import tempfile
import uuid

from .adapters.observations import normalize_path, read_document, _open_under
from .adapters.precedent_backend import PrecedentBackend
from .adapters.proposal_validation import valid_id
from .adoption import _git, _head, _base_files, _append, _read
from .application import now, iso, _receipt_view
from .domain.codec import digest
from .domain.effects import unittest_closure
from .domain.integration import file_map
from .effects import _gate
from .errors import LedgerError
from .storage.sqlite import EventStore
from .writers import assert_no_live_writers


def _files(executor, root, tree):
    result, total = {}, 0
    for name, (mode, oid) in _base_files(executor, root, tree).items():
        raw = _git(executor, root, 'cat-file', 'blob', oid)
        total += len(raw)
        if len(result) >= 1024 or total > 16 * 1024 * 1024:
            raise LedgerError('DOCUMENT_LIMIT')
        result[name] = {'oid': oid, 'sha256': hashlib.sha256(raw).hexdigest(), 'mode': mode, 'size': len(raw)}
    file_map(result)
    return result


def _blob(executor, root, raw, mode):
    oid = _git(executor, root, 'hash-object', '-w', '--stdin', data=raw).decode().strip()
    return {'oid': oid, 'sha256': hashlib.sha256(raw).hexdigest(), 'mode': mode, 'size': len(raw)}


def _merge(executor, root, base, ours, theirs):
    merged, conflicts = {}, set()
    for path in sorted(set(base) | set(ours) | set(theirs)):
        b, o, t = base.get(path), ours.get(path), theirs.get(path)
        if o == t or t == b:
            chosen = o
        elif o == b:
            chosen = t
        elif b and o and t and o['mode'] == t['mode']:
            # merge-file operates on bytes, without loading repository merge drivers or filters.
            with tempfile.TemporaryDirectory(prefix='vera-merge-', dir=Path(root) / '.verantyx') as temporary:
                paths = [Path(temporary) / name for name in ('ours', 'base', 'theirs')]
                for p, item in zip(paths, (o, b, t)):
                    p.write_bytes(_git(executor, root, 'cat-file', 'blob', item['oid']))
                result = subprocess.run(['git', 'merge-file', '-p', '-L', 'target', '-L', 'base', '-L', 'adopted',
                                         *map(str, paths)], capture_output=True, timeout=30)
            if result.returncode == 0:
                chosen = _blob(executor, root, result.stdout, o['mode'])
            else:
                conflicts.add(path)
                chosen = o  # explicit resolution is required; no conflicted bytes enter canonical state.
        else:
            conflicts.add(path)
            chosen = o
        if chosen is not None:
            merged[path] = chosen
    for path in list(merged):
        for i in range(1, len(path.split('/'))):
            parent = '/'.join(path.split('/')[:i])
            if parent in merged:
                conflicts.update((path, parent))
    # A valid preview uses the target's shape for directory/file conflicts.
    for path in list(merged):
        if path in conflicts and path not in ours:
            merged.pop(path)
    file_map(merged)
    return merged, sorted(conflicts)


def _directory(root, identifier):
    private = Path(root) / '.verantyx'
    parent = private / 'integrations'
    if private.is_symlink() or parent.is_symlink():
        raise LedgerError('STORE_PATH')
    parent.mkdir(mode=0o700, exist_ok=True)
    return parent / identifier


def _actual(root, expected):
    for name, item in expected.items():
        try:
            fd = _open_under(root, name)
            with os.fdopen(fd, 'rb') as handle:
                st = os.fstat(handle.fileno())
                if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
                    raise LedgerError('INTEGRATION_CHANGED')
                raw = handle.read(16 * 1024 * 1024 + 1)
            mode = '100755' if st.st_mode & 0o111 else '100644'
            if mode != item['mode'] or len(raw) != item['size'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise LedgerError('INTEGRATION_CHANGED')
        except OSError:
            raise LedgerError('INTEGRATION_CHANGED') from None


def _write(root, name, raw, mode):
    # Descriptor-relative traversal protects canonical writes against symlink parents.
    parts = normalize_path(name).split('/')
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    tempname = '.vera-' + uuid.uuid4().hex
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, 0o755, dir_fd=directory)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = child
        fd = os.open(tempname, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o755 if mode == '100755' else 0o644)
        os.replace(tempname, parts[-1], src_dir_fd=directory, dst_dir_fd=directory)
    finally:
        try: os.unlink(tempname, dir_fd=directory)
        except FileNotFoundError: pass
        os.close(directory)


def _replace(executor, object_root, destination, before, after):
    _actual(destination, before)
    # Refuse untracked or ignored files at every newly introduced destination.
    for name in set(after) - set(before):
        path = Path(destination) / name
        if path.is_symlink():
            raise LedgerError('INTEGRATION_CHANGED')
        if path.exists():
            removed = {p for p in set(before) - set(after) if p.startswith(name + '/')}
            if not path.is_dir() or not removed:
                raise LedgerError('INTEGRATION_CHANGED')
            # A tracked directory may become a file, but preserve every unrelated
            # ignored/untracked entry, including an empty directory or symlink.
            for directory, dirs, files in os.walk(path, followlinks=False):
                for child in dirs + files:
                    entry = Path(directory) / child
                    relative = entry.relative_to(destination).as_posix()
                    allowed = (relative in removed or any(p.startswith(relative + '/') for p in removed))
                    if entry.is_symlink() or not allowed:
                        raise LedgerError('INTEGRATION_CHANGED')
    for name in sorted(set(before) - set(after), key=lambda s: (-s.count('/'), s)):
        parts = name.split('/')
        directory = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
                os.close(directory); directory = child
            os.unlink(parts[-1], dir_fd=directory)
        finally:
            os.close(directory)
        parent = (Path(destination) / name).parent
        while parent != Path(destination):
            try: parent.rmdir()
            except OSError: break
            parent = parent.parent
    for name, item in after.items():
        if before.get(name) != item:
            _write(destination, name, _git(executor, object_root, 'cat-file', 'blob', item['oid']), item['mode'])


def _view(receipt, key):
    result = _receipt_view(receipt, key)
    for event in receipt['events']:
        if event['command_id'] == receipt['command_id'] and event['type'].startswith('Integration'):
            identifier = event['payload']['plan']['id'] if event['type'] == 'IntegrationPlanned' else event['payload']['integration_id']
            result.update(integration_id=identifier, integration=result['state']['integrations'][identifier])
    result['ok'] = result.get('integration', {}).get('status') not in ('INVALIDATED', 'OUTCOME_UNKNOWN', 'CHECK_FAILED')
    return result


def _checkout(executor, root, ref):
    root = Path(root).resolve()
    entries = executor.git(root, 'worktree', 'list', '--porcelain').split('\n\n')
    checked = False
    for entry in entries:
        lines = entry.splitlines()
        if 'branch ' + ref in lines:
            worktree = next((line[9:] for line in lines if line.startswith('worktree ')), '')
            if Path(worktree).resolve() != root:
                raise LedgerError('INTEGRATION_OTHER_CHECKOUT')
            checked = True
    return checked


def _source(store, root, state, item, precedent_path, clock):
    p = item['plan']
    executor = PrecedentBackend(precedent_path, expected_hash=p['backend_hash'])
    if _head(executor, root, p['target_ref']) != p['target_commit'] or digest(executor.snapshot(root)) != p['source_hash']:
        raise LedgerError('INTEGRATION_STALE')
    if _checkout(executor, root, p['target_ref']) != p['checked_out'] or digest(state['proposal']) != p['source_proposal_hash']:
        raise LedgerError('INTEGRATION_STALE')
    effect = state['effects'][state['adoptions'][p['adoption_id']]['plan']['effect_lease_id']]
    context = _gate(store, state, effect['lease']['plan'], clock)
    return executor, context


def plan_integration(root, cfg, run_id, adoption_id, precedent_path, key, *, branch, mode='merge',
                     message='Integrate adopted Vera change', clock=now):
    if not valid_id(key) or mode not in ('merge', 'rebase') or type(message) is not str or not 1 <= len(message.strip()) <= 2000:
        raise LedgerError('ARGUMENTS')
    intent = dict(operation='integration-plan', run_id=run_id, adoption_id=adoption_id, branch=branch, mode=mode,
                  message=message, precedent=str(Path(precedent_path).resolve()))
    with EventStore(root, cfg['project']['id'], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached: return _view(cached, key)
        previous, state = _read(store, run_id)
        adoption = state.get('adoptions', {}).get(adoption_id)
        if not adoption or adoption['status'] != 'ADOPTED': raise LedgerError('INTEGRATION_STAGE')
        executor = PrecedentBackend(precedent_path, expected_hash=adoption['plan']['backend_hash'])
        ref = branch if branch.startswith('refs/heads/') else 'refs/heads/' + branch
        _git(executor, root, 'check-ref-format', ref)
        target = _head(executor, root, ref)
        if target is None: raise LedgerError('INTEGRATION_TARGET')
        checked = _checkout(executor, root, ref)
        source = executor.snapshot(root)
        base_id, adopted = adoption['plan']['base_version'], adoption['receipt']['commit']
        # The adopted single change must share its base with the destination.
        _git(executor, root, 'merge-base', '--is-ancestor', base_id, target)
        base, ours, theirs = [_files(executor, root, tree) for tree in (base_id, target, adopted)]
        merged, conflicts = _merge(executor, root, base, ours, theirs)
        tests = adoption['plan']['tests']
        if any(name not in ours or merged.get(name) != ours[name] for name in tests):
            raise LedgerError('TEST_SCOPE')
        identifier = str(uuid.uuid4())
        path = _directory(root, identifier)
        executor.prepare(root, path, target)
        _replace(executor, root, path, ours, merged)
        plan = {'id': identifier, 'adoption_id': adoption_id, 'adoption_ref': adoption['receipt_ref'],
                'source_commit': adopted, 'source_proposal_hash': adoption['plan']['proposal_hash'], 'base_commit': base_id,
                'target_ref': ref, 'target_commit': target, 'checked_out': checked, 'source_hash': digest(source),
                'backend_hash': executor.fingerprint, 'mode': mode, 'files': merged, 'conflicts': conflicts, 'tests': tests,
                'allowed_paths': sorted(set(conflicts) | {p for p in set(base) | set(theirs) if base.get(p) != theirs.get(p)}),
                'message': message}
        return _view(_append(store, previous, [('IntegrationPlanned', {'plan': plan})], key, intent, clock), key)


def _candidate(executor, root, item):
    path = _directory(root, item['plan']['id'])
    if path.is_symlink() or not path.is_dir(): raise LedgerError('INTEGRATION_CHANGED')
    actual = executor.snapshot(path)
    if actual['base_version'] != item['plan']['target_commit']: raise LedgerError('INTEGRATION_CHANGED')
    _actual(path, item['files'])
    if any(name not in item['files'] and value['status'] != 'MISSING' for name, value in actual['files'].items()):
        raise LedgerError('INTEGRATION_CHANGED')
    return path


def resolve_integration(root, cfg, run_id, identifier, precedent_path, key, *, files, reason, clock=now):
    if (not valid_id(key) or type(files) is not dict or not files or len(files) > 32
            or type(reason) is not str or not 1 <= len(reason.strip()) <= 4000):
        raise LedgerError('ARGUMENTS')
    intent = dict(operation='integration-resolve', run_id=run_id, integration_id=identifier, files=files, reason=reason)
    with EventStore(root, cfg['project']['id'], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached: return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get('integrations', {}).get(identifier)
        if not item or item['status'] not in ('PLANNED', 'CONFLICTED', 'CHECK_FAILED', 'VERIFIED'):
            raise LedgerError('INTEGRATION_STAGE')
        executor, _ = _source(store, root, state, item, precedent_path, clock)
        path = _candidate(executor, root, item)
        if set(files) - set(item['plan']['allowed_paths']) or set(files) & set(item['plan']['tests']):
            raise LedgerError('PATH_SCOPE')
        merged = dict(item['files'])
        for name, content in files.items():
            normalize_path(name)
            if content is None:
                merged.pop(name, None)
            else:
                if type(content) is not str or len(content.encode()) > 100000: raise LedgerError('DOCUMENT_LIMIT')
                merged[name] = _blob(executor, root, content.encode(), merged.get(name, {}).get('mode', '100644'))
        file_map(merged)
        _replace(executor, root, path, item['files'], merged)
        payload = dict(integration_id=identifier, files=merged, resolved=sorted(files), reason=reason)
        return _view(_append(store, previous, [('IntegrationResolved', payload)], key, intent, clock), key)


def check_integration(root, cfg, run_id, identifier, precedent_path, key, *, clock=now, fault=None):
    intent = dict(operation='integration-verify', run_id=run_id, integration_id=identifier,
                  precedent=str(Path(precedent_path).resolve()))
    if not valid_id(key): raise LedgerError('ARGUMENTS')
    with EventStore(root, cfg['project']['id'], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached: return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get('integrations', {}).get(identifier)
        if not item or item['status'] not in ('PLANNED', 'VERIFIED', 'CHECK_FAILED', 'CHECK_STARTED') or item['conflicts']:
            raise LedgerError('INTEGRATION_STAGE')
        files_hash = digest(item['files'])
        raw = {'passed': False, 'output': '', 'interrupted': True}
        if item['status'] != 'CHECK_STARTED':
            executor, _ = _source(store, root, state, item, precedent_path, clock)
            path = _candidate(executor, root, item)
            start = _append(store, previous, [('IntegrationCheckStarted', dict(integration_id=identifier, files_hash=files_hash))],
                            'check-start-' + key, {'check_start': intent}, clock)
            previous = start['events']
            if fault: fault('after_start')
            try:
                raw = executor.module.run_tests(path, [path / p for p in item['plan']['tests']])
                _candidate(executor, root, item)
                executor.fresh()
            except (LedgerError, OSError, subprocess.SubprocessError):
                raw = {'passed': False, 'output': '', 'interrupted': True}
        payload = dict(integration_id=identifier, files_hash=files_hash, tests=item['plan']['tests'],
                       closure=unittest_closure(raw), result=raw)
        return _view(_append(store, previous, [('IntegrationChecked', payload)], key, intent, clock), key)


def _clean(executor, root, target):
    expected = _files(executor, root, target)
    _actual(root, expected)
    # A staged change is also unpublished work, even if the file bytes look clean.
    stages = {}
    for row in filter(None, executor.git(root, 'ls-files', '--stage', '-z').split('\0')):
        meta, name = row.split('\t', 1)
        mode, oid, stage = meta.split()
        if stage != '0': raise LedgerError('INTEGRATION_DIRTY')
        stages[name] = (mode, oid)
    if stages != _base_files(executor, root, target):
        raise LedgerError('INTEGRATION_DIRTY')


def _installed(executor, root, item):
    _actual(root, item['files'])
    removed = set(_base_files(executor, root, item['plan']['target_commit'])) - set(item['files'])
    for name in removed:
        if any(p.startswith(name + '/') for p in item['files']):
            continue  # This old file intentionally became an ancestor directory.
        path = Path(root) / name
        if path.exists() or path.is_symlink():
            raise LedgerError('INTEGRATION_CHANGED')


def _completed(executor, root, item, commit):
    if _head(executor, root, item['plan']['target_ref']) != commit:
        raise LedgerError('INTEGRATION_OUTCOME_UNKNOWN')
    if item['plan']['checked_out']:
        if not _checkout(executor, root, item['plan']['target_ref']):
            raise LedgerError('INTEGRATION_OUTCOME_UNKNOWN')
        _installed(executor, root, item)
        _clean(executor, root, commit)


@contextmanager
def _index_update(executor, root, commit):
    """Hold Git's index lock while canonical files/ref are updated; no filters are run."""
    raw_path = executor.git(root, 'rev-parse', '--git-path', 'index')
    index = Path(raw_path) if Path(raw_path).is_absolute() else Path(root) / raw_path
    if index.is_symlink() or (index.exists() and index.stat().st_nlink != 1):
        raise LedgerError('INTEGRATION_DIRTY')
    lock = Path(str(index) + '.lock')
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        raise LedgerError('INTEGRATION_DIRTY') from None
    installed = False
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            with tempfile.TemporaryDirectory(prefix='integrate-index-', dir=Path(root) / '.verantyx') as temporary:
                new_index = Path(temporary) / 'index'
                _git(executor, root, 'read-tree', commit, extra_env={'GIT_INDEX_FILE': str(new_index)})
                handle.write(read_document(new_index, 4 * 1024 * 1024)); handle.flush(); os.fsync(handle.fileno())
        def install():
            nonlocal installed
            os.replace(lock, index)
            installed = True
        yield install
    finally:
        if not installed:
            try: lock.unlink()
            except FileNotFoundError: pass


def authorize_integration(root, cfg, run_id, identifier, precedent_path, key, *, reason, ttl=300, clock=now):
    if (not valid_id(key) or type(ttl) is not int or not 1 <= ttl <= 3600
            or type(reason) is not str or not 1 <= len(reason.strip()) <= 4000):
        raise LedgerError('ARGUMENTS')
    intent = dict(operation='integration-authorize', run_id=run_id, integration_id=identifier, reason=reason, ttl=ttl,
                  precedent=str(Path(precedent_path).resolve()))
    with EventStore(root, cfg['project']['id'], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached: return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get('integrations', {}).get(identifier)
        if not item or item['status'] != 'VERIFIED': raise LedgerError('INTEGRATION_STAGE')
        assert_no_live_writers(root, cfg, root, clock=clock)
        executor, context = _source(store, root, state, item, precedent_path, clock)
        _candidate(executor, root, item)
        if item['plan']['checked_out']: _clean(executor, root, item['plan']['target_commit'])
        payload = dict(integration_id=identifier, plan_hash=digest(item['plan']), files_hash=digest(item['files']),
                       verification_ref=item['verification_ref'], basis_revision=state['revision'],
                       rule_context_hash=digest(context['rules']), expires_at=iso(clock() + timedelta(seconds=ttl)), reason=reason)
        return _view(_append(store, previous, [('PolicyContextRecorded', context), ('IntegrationAuthorized', payload)],
                             key, intent, clock), key)


def _commit(executor, root, item, timestamp):
    with tempfile.TemporaryDirectory(prefix='integration-index-', dir=Path(root) / '.verantyx') as temporary:
        env = {'GIT_INDEX_FILE': str(Path(temporary) / 'index'), 'GIT_AUTHOR_NAME': 'Verantyx', 'GIT_AUTHOR_EMAIL': 'verantyx@localhost',
               'GIT_COMMITTER_NAME': 'Verantyx', 'GIT_COMMITTER_EMAIL': 'verantyx@localhost',
               'GIT_AUTHOR_DATE': timestamp, 'GIT_COMMITTER_DATE': timestamp}
        _git(executor, root, 'read-tree', '--empty', extra_env=env)
        for name, blob in item['files'].items():
            _git(executor, root, 'update-index', '--add', '--cacheinfo', blob['mode'] + ',' + blob['oid'] + ',' + name, extra_env=env)
        tree = _git(executor, root, 'write-tree', extra_env=env).decode().strip()
        parents = ['-p', item['plan']['target_commit']]
        if item['plan']['mode'] == 'merge': parents += ['-p', item['plan']['source_commit']]
        return _git(executor, root, '-c', 'commit.gpgSign=false', 'commit-tree', tree, *parents,
                    data=(item['plan']['message'] + '\n\nVera-Integration: ' + item['plan']['id'] + '\n').encode(), extra_env=env).decode().strip()


def apply_integration(root, cfg, run_id, identifier, precedent_path, key, *, clock=now, fault=None):
    if not valid_id(key): raise LedgerError('ARGUMENTS')
    intent = dict(operation='integration-apply', run_id=run_id, integration_id=identifier,
                  precedent=str(Path(precedent_path).resolve()))
    with EventStore(root, cfg['project']['id'], create=True) as store, store.exclusive():
        cached = store.receipt(key, digest(intent))
        if cached: return _view(cached, key)
        previous, state = _read(store, run_id)
        item = state.get('integrations', {}).get(identifier)
        if not item or item['status'] not in ('AUTHORIZED', 'STARTED'): raise LedgerError('INTEGRATION_STAGE')
        recovered, error = item['status'] == 'STARTED', None
        p = item['plan']
        def check_authority(context):
            assert_no_live_writers(root, cfg, root, clock=clock)
            if iso(clock()) >= item['authorization']['expires_at']: raise LedgerError('LEASE_EXPIRED')
            if digest(context['rules']) != item['authorization']['rule_context_hash']: raise LedgerError('RULE_CHANGED')
        if recovered:
            commit = item['commit']
            try:
                executor = PrecedentBackend(precedent_path, expected_hash=p['backend_hash'])
                _completed(executor, root, item, commit)
            except (LedgerError, OSError, subprocess.SubprocessError): error = 'INTEGRATION_OUTCOME_UNKNOWN'
        else:
            try:
                executor, context = _source(store, root, state, item, precedent_path, clock)
                check_authority(context); _candidate(executor, root, item)
                if p['checked_out']: _clean(executor, root, p['target_commit'])
                commit = _commit(executor, root, item, iso(clock()))
                executor, context = _source(store, root, state, item, precedent_path, clock)
                check_authority(context)
            except (LedgerError, OSError, subprocess.SubprocessError) as exc:
                payload = dict(integration_id=identifier, reason=getattr(exc, 'code', 'INTEGRATION_FAILED'))
                return _view(_append(store, previous, [('IntegrationInvalidated', payload)], key, intent, clock), key)
            start = _append(store, previous, [('IntegrationStarted', dict(integration_id=identifier, commit=commit))],
                            'integration-start-' + identifier, {'integration_start': identifier}, clock)
            previous = start['events']
            if fault: fault('after_start')
            try:
                executor, context = _source(store, root, state, item, precedent_path, clock)
                check_authority(context); _candidate(executor, root, item)
                if p['checked_out']:
                    with _index_update(executor, root, commit) as install_index:
                        _clean(executor, root, p['target_commit'])
                        executor, context = _source(store, root, state, item, precedent_path, clock)
                        check_authority(context)
                        _replace(executor, root, root, _files(executor, root, p['target_commit']), item['files'])
                        if fault: fault('after_files')
                        _installed(executor, root, item)
                        if not _checkout(executor, root, p['target_ref']):
                            raise LedgerError('INTEGRATION_OUTCOME_UNKNOWN')
                        check_authority(context)
                        _git(executor, root, 'update-ref', p['target_ref'], commit, p['target_commit'])
                        install_index()
                else:
                    check_authority(context)
                    _git(executor, root, 'update-ref', p['target_ref'], commit, p['target_commit'])
                if fault: fault('after_ref')
                _completed(executor, root, item, commit)
            except (LedgerError, OSError, subprocess.SubprocessError) as exc:
                error = getattr(exc, 'code', 'INTEGRATION_FAILED')
        payload = dict(integration_id=identifier, commit=commit, outcome='OUTCOME_UNKNOWN' if error else 'INTEGRATED',
                       target_ref=p['target_ref'], files_hash=digest(item['files']), recovered=recovered, reason=error)
        return _view(_append(store, previous, [('IntegrationReceipt', payload)], key, intent, clock), key)


def review_integration(root, cfg, run_id, identifier):
    with EventStore(root, cfg['project']['id']) as store:
        _, state = _read(store, run_id)
        item = state.get('integrations', {}).get(identifier)
        if not item: raise LedgerError('INTEGRATION_STAGE')
        return dict(ok=True, integration_id=identifier, integration=item,
                    worktree=str(Path(root) / '.verantyx/integrations' / identifier), replay_only=True)
