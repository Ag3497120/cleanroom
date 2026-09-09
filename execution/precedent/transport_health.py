"""Observed response reliability, separate from code correctness and auth claims."""
import json,time
LOCAL={'ollama','pi','opencode','openclaw','hermes'}

def contract(result,role,owner):
    if not isinstance(result,dict):raise ValueError('Model response must be a JSON object')
    if role=='builder':
        files=result.get('files')
        valid=isinstance(files,dict) and bool(files) and all(isinstance(k,str) and isinstance(v,str) for k,v in files.items())
    elif role=='test_designer' and not (owner or '').startswith('harness:'):
        valid=isinstance(result.get('tests'),str) and bool(result['tests'].strip())
    else:
        valid=result.get('verdict') in {'PASS','FAIL','UNKNOWN'} and isinstance(result.get('findings'),list) and all(isinstance(x,str) for x in result['findings'])
    if not valid:raise ValueError('Model response does not match the '+role+' contract')
    return result

def recommendations(store,run,role,entries=None,now=None):
    from .adapters import discover
    if role not in {'builder','test_designer','reviewer'}:raise ValueError('Unknown role')
    state=store.run(run)
    if not state:raise ValueError('Unknown run')
    current=state.get('bindings',{}).get(role,'ollama' if role=='builder' else 'claude-cli')
    local=current in LOCAL;model=state['local_model'] if local else 'configured-default'
    now=time.time() if now is None else now
    rows=store.db.execute("SELECT at,body FROM ledger WHERE kind='transport_observation' AND at>=? ORDER BY seq DESC",(now-7*86400,)).fetchall()
    samples={}
    for at,raw in rows:
        entry=json.loads(raw)
        if entry['role']!=role or entry['requested_model']!=model:continue
        values=samples.setdefault(entry['provider'],[])
        if len(values)<20:values.append({**entry,'at':at})
    ranked=[]
    for entry in discover(store.home) if entries is None else entries:
        provider=entry['id']
        if not entry.get('automatic_inference') or (provider in LOCAL)!=local:continue
        observations=samples.get(provider,[]);success=sum(x['outcome']=='valid_response' for x in observations);n=len(observations)
        errors={kind:sum(x['outcome']==kind for x in observations) for kind in ('transport_error','json_error','contract_error')}
        ranked.append({'adapter':provider,'samples':n,'valid_responses':success,'failures':errors,'score':(success+1)/(n+2),'last_outcome':observations[0]['outcome'] if observations else None,'last_observed_at':observations[0]['at'] if observations else None,'current':provider==current,'authentication':'not_probed','code_correctness':'not_inferred'})
    ranked.sort(key=lambda x:(-x['score'],-x['valid_responses'],not x['current'],x['adapter']))
    best=next((x for x in ranked if x['valid_responses']>0),None)
    current_stats=next((x for x in ranked if x['current']),None)
    suggested=best['adapter'] if best and (not current_stats or best['score']>current_stats['score']) else (current if current_stats else None)
    remaining=state['limits']['local_calls' if local else 'cloud_calls']-state['usage']['local_calls' if local else 'cloud_calls']
    return {'run':run,'role':role,'current':current,'suggested':suggested,'alternatives':ranked,'requested_model':model,'remaining_calls':remaining,'window_days':7,'max_samples_per_adapter':20,'automatically_changed':False,'note':'Response format and transport observations only; not code quality or current authentication. No unobserved adapter is recommended. Recommendations stay within the current local/cloud budget class.'}


def response_schema(role,owner):
    if role=='builder':properties={'files':{'type':'object','additionalProperties':{'type':'string'},'minProperties':1}}
    elif role=='test_designer' and not (owner or '').startswith('harness:'):properties={'tests':{'type':'string','minLength':1}}
    else:properties={'verdict':{'type':'string','enum':['PASS','FAIL','UNKNOWN']},'findings':{'type':'array','items':{'type':'string'}}}
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
