"""Bounded Ollama settings trials. Limited probes are not general performance proofs."""
import json,time,uuid
from pathlib import Path
from .store import encode,sha
from .execution import apply_files,run_tests

DEFAULT={'temperature':0,'num_predict':4096,'num_ctx':8192}

def validate(options):
    if not isinstance(options,dict) or set(options)!=set(DEFAULT):raise ValueError('Specify only temperature, num_predict and num_ctx')
    if type(options['temperature']) not in {int,float} or not 0<=options['temperature']<=1:raise ValueError('Temperature must be 0..1')
    for key,low,high in [('num_predict',512,8192),('num_ctx',4096,32768)]:
        if type(options[key]) is not int or not low<=options[key]<=high:raise ValueError(key+' is outside the supported range')
    return dict(options)

def model_fingerprint(model):
    import re,urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3) as response:raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError('Metadata size limit')
        names={model,model+':latest' if ':' not in model.rsplit('/',1)[-1] else model}
        matches={entry.get('digest') for entry in json.loads(raw).get('models',[]) if entry.get('name') in names or entry.get('model') in names}
        if len(matches)!=1:raise ValueError('Model identity missing or ambiguous')
        digest=next(iter(matches))
        if not isinstance(digest,str) or not re.fullmatch(r'(?:sha256:)?[0-9a-fA-F]{64}',digest):raise ValueError('Invalid model digest')
        return digest.removeprefix('sha256:').lower()
    except Exception as error:raise ValueError('Cannot verify local model identity: '+str(error)) from error

def stored(store,model):
    for row in store.db.execute("SELECT body FROM ledger WHERE kind='profile_activated' ORDER BY seq DESC"):
        body=json.loads(row[0])
        if body['model']==model:return body
    return {'model':model,'options':dict(DEFAULT),'trial':None}

def active(store,model):
    body=stored(store,model)
    if body.get('trial') and (not body.get('model_digest') or model_fingerprint(model)!=body['model_digest']):raise ValueError('Model changed or profile identity missing; reset to defaults and compare again')
    return validate(body['options'])

def evaluate(engine,run,options):
    import fcntl
    options=validate(options)
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=engine.store.run(run)
        if not state:raise ValueError('Unknown run')
        if state.get('stopped') or time.time()>state['deadline']:raise ValueError('Execution stopped or expired')
        if state['limits']['local_calls']-state['usage']['local_calls']<4:raise ValueError('Profile comparison needs four remaining local calls')
        engine.check_main(run)
        fingerprint=model_fingerprint(state['local_model']);baseline=active(engine.store,state['local_model']);key=uuid.uuid4().hex[:12];folder=engine.home/'profile-trials'/key;folder.mkdir(parents=True)
        report={'id':key,'run':run,'model':state['local_model'],'model_digest':fingerprint,'baseline':baseline,'options':options,'cases':[],'scope':'Two fixed integer-function probes, not unseen-task performance or general correctness','activated':False}
        for label,settings in [('baseline',baseline),('candidate',options)]:
            for name,expression in [('identity','x'),('negate','-x')]:
                tree=folder/(label+'-'+name);tree.mkdir();before=engine.store.run(run)['usage'];started=time.monotonic()
                result={'profile':label,'case':name,'passed':False}
                try:
                    if model_fingerprint(state['local_model'])!=fingerprint:raise ValueError('Model changed during comparison')
                    answer=engine.model(run,'ollama','Return exactly JSON {"files":{"specimen.py":"complete Python module source"}}. Implement def f(x). For every Python integer x, f(x) returns '+('x numerically unchanged' if name=='identity' else 'its arithmetic negative')+'. Use no tools. Return the full module.',owner='profile:'+key,adapter='ollama',profile_options=settings)
                    apply_files(tree,answer['files'],['specimen.py']);source=(tree/'specimen.py').read_bytes()
                    test=folder/(label+'-'+name+'-test.py');test.write_text('import unittest\nfrom specimen import f\nclass Check(unittest.TestCase):\n def test_integers(self):\n  for x in [-13,0,7,10**30]:\n   with self.subTest(x=x):self.assertEqual(f(x),'+expression+')\n')
                    result['test']=run_tests(tree,[test]);result['passed']=result['test']['passed'] and source==(tree/'specimen.py').read_bytes() and model_fingerprint(state['local_model'])==fingerprint;result['source_digest']=sha(source)
                except Exception as error:result['error']=str(error)
                after=engine.store.run(run)['usage'];result['seconds']=time.monotonic()-started;result['tokens_observed']=after['tokens_observed']-before['tokens_observed'];report['cases'].append(result)
        report['eligible']=all(case['passed'] for case in report['cases']);engine.emit(run,'profile_trial',report);(folder/'report.json').write_text(encode(report));return report

def activate(engine,trial):
    import fcntl
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        record=next((json.loads(row[0]) for row in engine.store.db.execute("SELECT body FROM ledger WHERE kind='profile_trial'") if json.loads(row[0])['id']==trial),None)
        if not record or not record['eligible']:raise ValueError('A passing saved profile trial is required')
        if not record.get('model_digest') or model_fingerprint(record['model'])!=record['model_digest']:raise ValueError('Trial model changed or is unverified; compare again')
        if active(engine.store,record['model'])!=record['baseline']:raise ValueError('Active settings changed; compare again before activation')
        event={'model':record['model'],'model_digest':record['model_digest'],'options':record['options'],'previous':record['baseline'],'trial':trial,'source':'operator'};engine.store.event('profile_activated',event);return event

def reset(engine,model):
    import fcntl
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        event={'model':model,'options':dict(DEFAULT),'previous':validate(stored(engine.store,model)['options']),'trial':None,'source':'operator_reset'};engine.store.event('profile_activated',event);return event

def suggest(store,run):
    """Read-only heuristic from recent matching failures; never an adoption decision."""
    store.assert_ledger();state=store.run(run)
    if not state:raise ValueError('Unknown run')
    baseline=validate(stored(store,state['local_model'])['options']);samples=[];cutoff=time.time()-7*86400
    for seq,at,raw in store.db.execute("SELECT seq,at,body FROM ledger WHERE kind='model_call' ORDER BY seq DESC"):
        body=json.loads(raw)
        if at<cutoff or body.get('run')!=run or body.get('provider')!='ollama' or body.get('model')!=state['local_model']:continue
        if str(body.get('owner','')).startswith('profile:') or body.get('profile_options')!=baseline:continue
        samples.append({'seq':seq,'done_reason':body.get('done_reason'),'response_rejected':body.get('response_rejected',False)})
        if len(samples)==2:break
    result={'run':run,'model':state['local_model'],'baseline':baseline,'proposed':False,'evidence':samples,'scope':'Heuristic from the latest two matching non-probe calls in this run within seven days. Matching model names do not prove historical weight identity. Trial and explicit activation remain required; improvement is unverified.'}
    if len(samples)<2 or not all(s['done_reason']=='length' and s['response_rejected'] is True for s in samples):result['reason']='同じ設定で直近2回続けて出力上限に達した記録がないため、設定案は作りません。'
    elif baseline['num_predict']>=8192:result['reason']='出力上限は比較機能の対応範囲の最大値です。仕事の分割など別の対応が必要です。'
    else:result.update(proposed=True,options={**baseline,'num_predict':min(8192,baseline['num_predict']*2)},reason='同じ設定の直近2回が出力上限で打ち切られたため、出力上限を増やす比較案です。改善は未検証です。')
    return result
