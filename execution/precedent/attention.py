"""Explicit elapsed intervals; not proof that a human was watching throughout."""
import fcntl,json,time,uuid

CATEGORIES={'review':'確認','decision':'判断','rework':'修正'}

def intervals(store):
    records={}
    for seq,raw in store.db.execute("SELECT seq,body FROM ledger WHERE kind IN ('attention_started','attention_finished','attention_abandoned') ORDER BY seq"):
        body=json.loads(raw);key=body['interval']
        if body.get('state')=='open':records[key]={**body,'start_seq':seq}
        elif key in records:records[key].update(body,end_seq=seq)
    return list(records.values())

def summary(store,run):
    rows=[r for r in intervals(store) if r['run']==run]
    completed=[r for r in rows if r['state']=='completed']
    return {'intervals':rows,'completed_elapsed_seconds':sum(r['seconds'] for r in completed) if completed else None,'by_category':{k:sum(r['seconds'] for r in completed if r['category']==k) for k in CATEGORIES},'unfinished_count':sum(r['state']=='open' for r in rows),'abandoned_count':sum(r['state']=='abandoned' for r in rows),'scope':'Explicitly started/stopped elapsed intervals, not verified human presence. Missing intervals are unknown; no baseline or savings inferred.'}

class Recorder:
    def __init__(self):self.owner=uuid.uuid4().hex;self.started={}
    def start(self,store,run,category):
        if category not in CATEGORIES:raise ValueError('Unknown attention category')
        with (store.home/'attention.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if not store.run(run):raise ValueError('Unknown run')
            if any(r['state']=='open' for r in intervals(store)):raise ValueError('終了していない計測があります。対象の実行で終了するか、時間不明で閉じてください。')
            key=uuid.uuid4().hex;started=time.monotonic()
            body={'interval':key,'run':run,'category':category,'owner':self.owner,'state':'open','started_at':time.time(),'seconds':None}
            store.event('attention_started',body);self.started[key]=started;return body
    def close(self,store,run,key,abandon=False):
        with (store.home/'attention.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            row=next((r for r in intervals(store) if r['interval']==key),None)
            if not row or row['run']!=run or row['state']!='open':raise ValueError('この実行の未終了の計測を選択してください。')
            if not abandon and (row['owner']!=self.owner or key not in self.started):raise ValueError('アプリを再起動した計測は正確に終了できません。時間不明で閉じてください。')
            seconds=None if abandon else max(0,time.monotonic()-self.started[key])
            body={'interval':key,'run':run,'state':'abandoned' if abandon else 'completed','ended_at':time.time(),'seconds':seconds}
            store.event('attention_abandoned' if abandon else 'attention_finished',body);self.started.pop(key,None);return body
