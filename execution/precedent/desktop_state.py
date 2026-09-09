"""Timestamped desktop observations. They never grant an inference transport."""
import time
from .store import encode

DESKTOPS={'claude-desktop','chatgpt-desktop','codex-desktop'}
STATUSES={'auth_required','control_unavailable','observed_input','identity_unverified'}
SURFACES={'chat','code','unknown'}


def record(store,adapter,surface,bundle_id,status,reason,source='operator',ttl=900):
    from .adapters import discover
    if adapter not in DESKTOPS or surface not in SURFACES or status not in STATUSES:raise ValueError('Invalid desktop observation')
    if source not in {'operator','cua'} or not isinstance(reason,str) or not reason.strip() or len(reason)>500:raise ValueError('Invalid observation source or reason')
    if type(ttl) is not int or not 0<ttl<=3600:raise ValueError('Observation lifetime must be 1–3600 seconds')
    entry=next(e for e in discover() if e['id']==adapter)
    if not bundle_id or bundle_id!=entry['bundle_id']:raise ValueError('Desktop bundle identity mismatch')
    now=time.time();body={'adapter':adapter,'surface':surface,'bundle_id':bundle_id,'status':status,'reason':reason,'source':source,'observed_at':now,'expires_at':now+ttl,'automatic_inference':False}
    store.db.execute('INSERT OR REPLACE INTO desktop_surfaces VALUES(?,?)',(adapter+':'+surface,encode(body)));store.db.commit();store.event('desktop_surface_observed',body);return body


def observations(store,adapter,bundle_id,now=None):
    import json
    now=time.time() if now is None else now
    result=[]
    for row in store.db.execute('SELECT body FROM desktop_surfaces'):
        body=json.loads(row[0])
        if body['adapter']!=adapter:continue
        status='identity_changed' if body['bundle_id']!=bundle_id else 'stale' if now>=body['expires_at'] else body['status']
        result.append({**body,'effective_status':status,'automatic_inference':False})
    return sorted(result,key=lambda x:x['observed_at'],reverse=True)
