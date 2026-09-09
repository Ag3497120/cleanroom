"""Replayable integration of an adopted change; all live Git work is outside here."""
from copy import deepcopy
from datetime import datetime, timedelta
import re

EVENT_ACTORS = {
    'IntegrationPlanned': 'kernel', 'IntegrationResolved': 'local_cli',
    'IntegrationCheckStarted': 'execution_gateway', 'IntegrationChecked': 'scope_verifier',
    'IntegrationAuthorized': 'local_cli', 'IntegrationStarted': 'execution_gateway',
    'IntegrationInvalidated': 'execution_gateway', 'IntegrationReceipt': 'execution_backend',
}


def oid(value):
    from .events import require
    require(type(value) is str and re.fullmatch(r'(?:[a-f0-9]{40}|[a-f0-9]{64})', value) is not None)


def file_map(value):
    from .events import fields, require, hash_value
    from ..adapters.observations import normalize_path
    require(type(value) is dict and len(value) <= 1024)
    total = 0
    for name, item in value.items():
        normalize_path(name)
        fields(item, ('oid', 'sha256', 'mode', 'size'))
        oid(item['oid']); hash_value(item['sha256'])
        require(item['mode'] in ('100644', '100755'))
        require(type(item['size']) is int and 0 <= item['size'] <= 16 * 1024 * 1024)
        total += item['size']
        require(not any('/'.join(name.split('/')[:i]) in value for i in range(1, len(name.split('/')))))
    require(total <= 16 * 1024 * 1024)


def validate_payload(kind, payload):
    from .events import fields, require, uuid_value, hash_value, timestamp
    from ..adapters.observations import normalize_path
    if kind == 'IntegrationPlanned':
        fields(payload, ('plan',))
        p = payload['plan']
        fields(p, ('id', 'adoption_id', 'adoption_ref', 'source_commit', 'source_proposal_hash',
                   'base_commit', 'target_ref', 'target_commit', 'checked_out', 'source_hash',
                   'backend_hash', 'mode', 'files', 'conflicts', 'tests', 'allowed_paths', 'message'))
        uuid_value(p['id']); uuid_value(p['adoption_id'])
        for k in ('source_commit', 'base_commit', 'target_commit'): oid(p[k])
        for k in ('source_proposal_hash', 'source_hash', 'backend_hash'): hash_value(p[k])
        require(type(p['adoption_ref']) is str and len(p['adoption_ref']) == 73)
        require(type(p['target_ref']) is str and p['target_ref'].startswith('refs/heads/'))
        require(type(p['checked_out']) is bool and p['mode'] in ('merge', 'rebase'))
        file_map(p['files'])
        for key in ('conflicts', 'tests', 'allowed_paths'):
            require(type(p[key]) is list and len(set(p[key])) == len(p[key]) and len(p[key]) <= 1024)
            for name in p[key]: normalize_path(name)
        require(1 <= len(p['tests']) <= 16 and set(p['conflicts']) <= set(p['allowed_paths']))
        require(type(p['message']) is str and 1 <= len(p['message'].strip()) <= 2000)
        return
    require(type(payload) is dict)
    uuid_value(payload.get('integration_id'))
    if kind == 'IntegrationResolved':
        fields(payload, ('integration_id', 'files', 'resolved', 'reason'))
        file_map(payload['files'])
        require(type(payload['resolved']) is list and len(set(payload['resolved'])) == len(payload['resolved']))
        for path in payload['resolved']: normalize_path(path)
        require(type(payload['reason']) is str and 1 <= len(payload['reason'].strip()) <= 4000)
    elif kind == 'IntegrationCheckStarted':
        fields(payload, ('integration_id', 'files_hash'))
        hash_value(payload['files_hash'])
    elif kind == 'IntegrationChecked':
        fields(payload, ('integration_id', 'files_hash', 'tests', 'closure', 'result'))
        hash_value(payload['files_hash'])
        require(type(payload['tests']) is list and type(payload['result']) is dict)
        from .effects import unittest_closure
        require(payload['closure'] == unittest_closure(payload['result']))
    elif kind == 'IntegrationAuthorized':
        fields(payload, ('integration_id', 'plan_hash', 'files_hash', 'verification_ref', 'basis_revision',
                         'rule_context_hash', 'expires_at', 'reason'))
        for k in ('plan_hash', 'files_hash', 'rule_context_hash'): hash_value(payload[k])
        require(type(payload['verification_ref']) is str and len(payload['verification_ref']) == 73)
        require(type(payload['basis_revision']) is int and payload['basis_revision'] > 0)
        timestamp(payload['expires_at'])
        require(type(payload['reason']) is str and 1 <= len(payload['reason'].strip()) <= 4000)
    elif kind == 'IntegrationStarted':
        fields(payload, ('integration_id', 'commit'))
        oid(payload['commit'])
    elif kind == 'IntegrationInvalidated':
        fields(payload, ('integration_id', 'reason'))
        require(type(payload['reason']) is str and 1 <= len(payload['reason']) <= 160)
    elif kind == 'IntegrationReceipt':
        fields(payload, ('integration_id', 'commit', 'outcome', 'target_ref', 'files_hash', 'recovered', 'reason'))
        oid(payload['commit']); hash_value(payload['files_hash'])
        require(payload['outcome'] in ('INTEGRATED', 'OUTCOME_UNKNOWN') and type(payload['recovered']) is bool)
        require(type(payload['target_ref']) is str and type(payload['reason']) in (str, type(None)))
        require((payload['outcome'] == 'INTEGRATED') == (payload['reason'] is None))


def apply_event(state, event):
    from .events import require, citation
    from .codec import digest
    kind, p = event['type'], event['payload']
    if kind not in EVENT_ACTORS:
        return
    items = state.setdefault('integrations', {})
    if kind == 'IntegrationPlanned':
        plan = p['plan']
        adoption = state.get('adoptions', {}).get(plan['adoption_id'])
        require(adoption and adoption['status'] == 'ADOPTED', 'STORE_INTEGRITY')
        require(adoption['receipt_ref'] == plan['adoption_ref'] and adoption['receipt']['commit'] == plan['source_commit'], 'STORE_INTEGRITY')
        require(adoption['plan']['base_version'] == plan['base_commit'] and adoption['plan']['tests'] == plan['tests'], 'STORE_INTEGRITY')
        require(adoption['plan']['proposal_hash'] == plan['source_proposal_hash'] == digest(state['proposal']), 'STORE_INTEGRITY')
        require(plan['backend_hash'] == adoption['plan']['backend_hash'] and plan['id'] not in items, 'STORE_INTEGRITY')
        items[plan['id']] = {'status': 'CONFLICTED' if plan['conflicts'] else 'PLANNED', 'plan': deepcopy(plan),
                             'files': deepcopy(plan['files']), 'conflicts': list(plan['conflicts']),
                             'source_ref': citation(event), 'history': [citation(event)]}
        return
    item = items.get(p['integration_id'])
    require(item is not None, 'STORE_INTEGRITY')
    if kind == 'IntegrationResolved':
        require(item['status'] in ('PLANNED', 'CONFLICTED', 'CHECK_FAILED', 'VERIFIED'), 'STORE_INTEGRITY')
        before = item['files']
        changed = {k for k in set(before) | set(p['files']) if before.get(k) != p['files'].get(k)}
        require(changed <= set(item['plan']['allowed_paths']), 'STORE_INTEGRITY')
        require(set(p['resolved']) <= set(item['plan']['allowed_paths']), 'STORE_INTEGRITY')
        require(not (changed & set(item['plan']['tests'])), 'STORE_INTEGRITY')
        item.update(files=deepcopy(p['files']), conflicts=[n for n in item['conflicts'] if n not in p['resolved']])
        item['status'] = 'CONFLICTED' if item['conflicts'] else 'PLANNED'
        item.pop('verification', None); item.pop('verification_ref', None)
    elif kind == 'IntegrationCheckStarted':
        require(item['status'] in ('PLANNED', 'VERIFIED', 'CHECK_FAILED') and not item['conflicts'], 'STORE_INTEGRITY')
        require(p['files_hash'] == digest(item['files']), 'STORE_INTEGRITY')
        item.update(status='CHECK_STARTED')
    elif kind == 'IntegrationChecked':
        require(item['status'] == 'CHECK_STARTED' and p['files_hash'] == digest(item['files']), 'STORE_INTEGRITY')
        require(p['tests'] == item['plan']['tests'], 'STORE_INTEGRITY')
        item.update(status='VERIFIED' if p['closure'] == 'BOUNDED' else 'CHECK_FAILED',
                    verification=deepcopy(p), verification_ref=citation(event))
    elif kind == 'IntegrationAuthorized':
        require(item['status'] == 'VERIFIED' and p['verification_ref'] == item['verification_ref'], 'STORE_INTEGRITY')
        require(p['plan_hash'] == digest(item['plan']) and p['files_hash'] == digest(item['files']), 'STORE_INTEGRITY')
        require(p['basis_revision'] == state['command_start_revision'], 'STORE_INTEGRITY')
        require(digest(state['proposal']) == item['plan']['source_proposal_hash'], 'STORE_INTEGRITY')
        require(state['policy_context'] and p['rule_context_hash'] == digest(state['policy_context']['rules']), 'STORE_INTEGRITY')
        recorded = datetime.strptime(event['recorded_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        expiry = datetime.strptime(p['expires_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
        require(recorded < expiry <= recorded + timedelta(seconds=3600), 'STORE_INTEGRITY')
        item.update(status='AUTHORIZED', authorization=deepcopy(p), authorization_ref=citation(event))
    elif kind == 'IntegrationStarted':
        require(item['status'] == 'AUTHORIZED' and event['recorded_at'] < item['authorization']['expires_at'], 'STORE_INTEGRITY')
        require(digest(state['proposal']) == item['plan']['source_proposal_hash'], 'STORE_INTEGRITY')
        require(state['policy_context'] and item['authorization']['rule_context_hash'] == digest(state['policy_context']['rules']), 'STORE_INTEGRITY')
        item.update(status='STARTED', commit=p['commit'], started_ref=citation(event))
    elif kind == 'IntegrationInvalidated':
        require(item['status'] == 'AUTHORIZED', 'STORE_INTEGRITY')
        item.update(status='INVALIDATED', reason=p['reason'])
    else:
        require(item['status'] == 'STARTED' and item['commit'] == p['commit'], 'STORE_INTEGRITY')
        require(p['target_ref'] == item['plan']['target_ref'] and p['files_hash'] == digest(item['files']), 'STORE_INTEGRITY')
        item.update(status=p['outcome'], receipt=deepcopy(p), receipt_ref=citation(event))
    item['history'].append(citation(event))
