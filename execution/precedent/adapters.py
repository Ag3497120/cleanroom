"""App identities and portable task capsules. Presence is not automation capability."""
from .reconsider import task_rules
import json,plistlib,shutil,subprocess,time,uuid
from pathlib import Path
from .store import encode,sha

CATALOG=[
 {'id':'ollama','name':'Ollama','command':'ollama','app':'Ollama','mode':'inference','role':'local'},
 {'id':'claude-cli','name':'Claude Code','command':'claude','app':None,'mode':'inference','role':'cloud'},
 {'id':'codex-cli','name':'Codex CLI','command':'codex','app':None,'mode':'inference','role':'cloud'},
 {'id':'claude-desktop','name':'Claude Desktop','command':None,'app':'Claude','mode':'handoff','role':'desktop'},
 {'id':'chatgpt-desktop','name':'ChatGPT','command':None,'app':'ChatGPT','mode':'handoff','role':'desktop'},
 {'id':'codex-desktop','name':'Codex desktop surface','command':None,'app':'ChatGPT','mode':'handoff','role':'desktop'},
 {'id':'opencode','name':'OpenCode · local Ollama','command':'opencode','app':'OpenCode','mode':'inference','role':'local'},
 {'id':'openclaw','name':'OpenClaw · local Ollama','command':'openclaw','app':None,'mode':'inference','role':'local'},
 {'id':'pi','name':'pi · local Ollama','command':'pi','app':None,'mode':'inference','role':'local'},
 {'id':'hermes','name':'Hermes · local Ollama (64K+)','command':'hermes','app':None,'mode':'inference','role':'local','minimum_context_tokens':64000},
]

def discover(home=None):
    results=[]
    for spec in CATALOG:
        entry=dict(spec);entry['executable']=shutil.which(spec['command']) if spec['command'] else None
        if spec['id']=='pi':
            from .pi_transport import executable
            entry['executable']=executable()
        if spec['id']=='opencode':
            from .opencode_transport import executable
            entry['executable']=executable()
        if spec['id']=='openclaw':
            from .openclaw_transport import executable
            entry['executable']=executable()
        if spec['id']=='hermes':
            from .hermes_transport import executable
            entry['executable']=executable()
        app=Path('/Applications')/(str(spec['app'])+'.app') if spec['app'] else None
        entry['app_path']=str(app) if app and app.exists() else None;entry['bundle_id']=None;entry['version']=None
        if entry['app_path']:
            try:
                with (app/'Contents/Info.plist').open('rb') as f:info=plistlib.load(f)
                entry['bundle_id']=info.get('CFBundleIdentifier');entry['version']=info.get('CFBundleShortVersionString')
            except (OSError,ValueError):pass
        entry['available']=bool(entry['executable'] or entry['app_path'])
        entry['automatic_inference']=bool(entry['executable'] and entry['mode']=='inference')
        entry['authentication']='not_probed'
        entry['note']='Presence only. No desktop automation or authentication inferred.'
        if entry['bundle_id']=='com.openai.codex':entry['note']='Installed ChatGPT.app has Codex bundle identity; desktop surfaces are not yet separately automated.'
        results.append(entry)
    if home is not None:
        from .store import Store
        from .desktop_state import observations
        store=Store(home)
        try:
            for entry in results:
                entry['desktop_observations']=observations(store,entry['id'],entry['bundle_id'])
        finally:store.close()
    return results

def require_inference(adapter):
    entry=next((x for x in discover() if x['id']==adapter),None)
    if not entry or not entry['automatic_inference']:raise RuntimeError('Adapter is not a verified inference transport; use a handoff capsule: '+adapter)
    return entry

def _capsule(store,run,adapter):
    entry=next(x for x in discover(store.home) if x['id']==adapter)
    state=store.run(run)
    if not state:raise ValueError('Unknown run')
    from .execution import git,safe_path
    repo=Path(state['repository'])
    if git(repo,'rev-parse','HEAD')!=state['base'] or git(repo,'status','--porcelain'):raise RuntimeError('HUMAN_EDIT_CONFLICT: target changed before handoff')
    contexts={};eligibility={}
    for task in state['tasks']:
        resolution=handoff_eligibility(state,task)
        eligibility[task['id']]=resolution
        if not resolution['eligible']:continue
        dependency=dependency_snapshot(store,run,task)
        source={}
        for name in task['editable']:
            safe_path(repo,name)
            source[name]=dependency['files'].get(name,git(repo,'show',state['base']+':'+name) if (repo/name).exists() else '')
        public={}
        for name in task['tests']:
            safe_path(repo,name)
            content=git(repo,'show',state['base']+':'+name)
            if sha(content)!=state['test_hashes'][name]:raise ValueError('Frozen public test baseline mismatch')
            public[name]=content
        contexts[task['id']]={'dependencies':dependency,'source':source,'public_tests':public,'source_digest':sha(encode(source)),'test_digests':{name:sha(text) for name,text in public.items()}}
        if len(encode(contexts).encode())>state['limits']['max_source_bytes']:raise ValueError('Handoff source context budget exceeded')
    if git(repo,'rev-parse','HEAD')!=state['base'] or git(repo,'status','--porcelain'):raise RuntimeError('HUMAN_EDIT_CONFLICT: target changed while preparing handoff')
    key=uuid.uuid4().hex[:12]
    body={'schema':'precedent-handoff/5','id':key,'adapter':entry,'run':run,'base':state['base'],'repository':state['repository'],'tasks':state['tasks'],'decisions':state['decisions'],'status':state['status'],'policies':state['rule_snapshot'],'budget_remaining':{k:state['limits'][k]-state['usage'][k] for k in ('local_calls','cloud_calls')},'candidates':[{'id':c['id'],'state':c['state'],'source_digest':c.get('source_digest'),'branch':c['branch']} for c in store.candidates(run)],'instruction':'Continue only within these scoped decisions. Existing candidates are evidence, not authority. Do not merge or execute external effects. Return proposals for Precedent verification.','created':time.time(),'transmission':'not_sent'}
    body['contexts']=contexts;body['eligibility']=eligibility;body['task_rule_snapshots']=state.get('task_rule_snapshots',{})
    body['instruction']+=' Only tasks marked eligible may be implemented. Use the included frozen source and public tests; do not inspect the host filesystem. Return one JSON response matching response_contract, choosing an authorized task and its exact option. Include full replacement files only; do not supply a verdict.'
    body['response_contract']={'schema':'precedent-response/1','handoff':key,'base':state['base'],'task':'one authorized task id','option':'one exact task option, or Implement the requirement','files':{'editable/path.py':'entire replacement source'}}
    store.db.execute('INSERT INTO handoffs(id,body) VALUES(?,?)',(key,encode(body)));store.db.commit()
    folder=store.home/'handoffs';folder.mkdir(exist_ok=True);path=folder/(key+'.json');path.write_text(encode(body))
    markdown=path.with_suffix('.md');markdown.write_text('# Precedent task handoff\n\n'+body['instruction']+'\n\n```json\n'+json.dumps(body,ensure_ascii=False,indent=2)+'\n```\n')
    store.event('handoff_prepared',{'run':run,'adapter':adapter,'capsule':str(path),'digest':sha(path.read_bytes()),'transmitted':False})
    return {'capsule':str(path),'readable':str(markdown),'adapter':adapter,'sent':False}

def dependency_snapshot(store,run,task):
    if not task.get('depends_on'):return {'selection':{},'files':{}}
    from .engine import Engine
    from .dependencies import context
    engine=Engine(store.home)
    try:
        state=store.run(run)
        selection=state.get('dependency_bindings',{}).get(task['id'])
        if not selection:raise ValueError('Unresolved combined baseline')
        files,_=context(engine,run,task)
        return {'selection':selection,'files':files}
    finally:engine.close()

def check_dependency_snapshot(store,body,task):
    if not task.get('depends_on'):return
    if body.get('schema') not in {'precedent-handoff/4','precedent-handoff/5'}:raise ValueError('Dependency handoff requires a new capsule')
    current=dependency_snapshot(store,body['run'],task)
    if current!=body['contexts'][task['id']].get('dependencies'):raise ValueError('Handoff dependency selection changed')


def _bind(store,run,role,adapter):
    if role not in {'builder','test_designer','reviewer'}:raise ValueError('Unknown binding role')
    require_inference(adapter);state=store.run(run)
    if not state:raise ValueError('Unknown run')
    from .capabilities import require_compatible
    require_compatible(adapter,state.get('local_model',''))
    before=dict(state['usage']);old=state.setdefault('bindings',{}).get(role)
    state['bindings'][role]=adapter;store.run(run,state)
    store.event('adapter_replaced',{'run':run,'role':role,'old':old,'new':adapter,'usage_preserved':before==store.run(run)['usage'],'base':state['base']})
    return state['bindings']


def import_response(engine,path):
    """Import a proposal once. Desktop identity is never authenticated by a JSON file."""
    import fcntl
    from .policy import decide
    from .execution import safe_path
    path=Path(path)
    if path.stat().st_size>1_000_000:raise ValueError('Response size limit')
    response=json.loads(path.read_text())
    if not isinstance(response,dict) or response.get('schema')!='precedent-response/1':raise ValueError('Unknown response schema')
    digest=sha(encode(response));store=engine.store
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        row=store.db.execute('SELECT body,response_digest,result FROM handoffs WHERE id=?',(response.get('handoff'),)).fetchone()
        if not row:raise ValueError('Unknown handoff; legacy exports cannot import responses')
        if row[1]:
            if row[1]!=digest:raise ValueError('Handoff already consumed by a different response')
            return json.loads(row[2]) if row[2] else {'state':'interrupted','run':json.loads(row[0])['run'],'reason':'Import was interrupted; inspect retained candidates before a new handoff'}
        capsule_body=json.loads(row[0]);run=capsule_body['run'];state=store.run(run)
        engine.check_main(run)
        if state.get('stopped'):raise ValueError('Run is stopped')
        if response.get('base')!=state['base']:raise ValueError('Response baseline mismatch')
        for field in ('tasks','decisions','policies'):
            actual=state['rule_snapshot'] if field=='policies' else state[field]
            if actual!=capsule_body[field]:raise ValueError('Handoff scope changed: '+field)
        if state.get('task_rule_snapshots',{})!=capsule_body.get('task_rule_snapshots',{}):raise ValueError('Handoff task judgments changed')
        task=next((t for t in state['tasks'] if t['id']==response.get('task')),None)
        if not task:raise ValueError('Unknown task')
        eligible=handoff_eligibility(state,task)
        if not eligible['eligible']:raise ValueError(eligible['reason'])
        if capsule_body.get('schema') in {'precedent-handoff/3','precedent-handoff/4','precedent-handoff/5'} and task['id'] not in capsule_body['contexts']:raise ValueError('Task was not authorized in this handoff')
        check_dependency_snapshot(store,capsule_body,task)
        decision=eligible['decision']
        if decision['action'] not in {'APPLY','STAGE','FORK'}:raise ValueError('Task decision does not authorize implementation')
        recorded=state['decisions'].get(task['id'],{})
        if recorded.get('action') in {'DEFER','ESCALATE','STOP'}:raise ValueError('Recorded task decision is held')
        if response.get('option') not in task.get('options',['Implement the requirement']):raise ValueError('Unknown alternative')
        files=response.get('files')
        if not isinstance(files,dict) or not files or set(files)-set(task['editable']):raise ValueError('Response exceeds editable scope')
        for name,content in files.items():
            safe_path(Path(state['repository']),name)
            if not isinstance(content,str) or len(content.encode())>100_000:raise ValueError('Invalid source content')
        if len(store.candidates(run))>=state['limits']['max_total_candidates']:raise ValueError('Candidate budget exhausted')
        store.db.execute('UPDATE handoffs SET response_digest=? WHERE id=?',(digest,response['handoff']));store.db.commit()
        previous={c['id'] for c in store.candidates(run)}
        delivered=store.db.execute('SELECT body FROM deliveries WHERE id=?',(response['handoff'],)).fetchone()
        provenance=json.loads(delivered[0]) if delivered else {}
        response['_origin']='inference_transport_return' if provenance.get('response_digest')==digest else 'operator_supplied_unverified'
        store.event('handoff_response_received',{'run':run,'handoff':response['handoff'],'digest':digest,'origin':response['_origin'],'task':task['id']})
        try:
            ready=engine.build_task(run,task,decision['action'],incoming=response)
            engine.check_main(run)
            result={'state':'verified' if ready else 'review_required','verified':ready}
        except Exception as error:
            result={'state':'review_required','verified':[],'error':str(error)}
        result.update({'run':run,'handoff':response['handoff'],'candidates':[c['id'] for c in store.candidates(run) if c['id'] not in previous]})
        current=store.run(run)
        held=current.get('failure_decisions',{}).get(task['id'],{}).get('action') in {'DEFER','ESCALATE','STOP'}
        if held:result['failure_decision']=current['failure_decisions'][task['id']]
        elif result['verified']:current['status'][task['id']]='ready'
        elif not any(c['task']==task['id'] and c['state']=='verified' for c in store.candidates(run)):current['status'][task['id']]='deferred'
        current['decisions'].setdefault(task['id'],decision);store.run(run,current)
        store.db.execute('UPDATE handoffs SET result=? WHERE id=?',(encode(result),response['handoff']));store.db.commit()
        store.event('handoff_response_checked',result);engine.bundle(run)
        return result


def bind(store,run,role,adapter):
    import fcntl
    with (store.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _bind(store,run,role,adapter)


def handoff_eligibility(state,task):
    from .policy import decide
    resolution=decide(task_rules(state,task['id']),state['repository'],task['event'],task.get('facts',{}),task.get('evidence',{}))
    reason=None
    if state.get('stopped'):reason='Run is stopped'
    elif task.get('depends_on') and task['id'] not in state.get('dependency_bindings',{}):reason='Unresolved combined baseline'
    elif resolution['action'] not in {'APPLY','STAGE','FORK'}:reason='Task decision does not authorize implementation'
    elif state['decisions'].get(task['id'],{}).get('action') in {'DEFER','ESCALATE','STOP'}:reason='Recorded task decision is held'
    elif state['status'][task['id']] in {'defer','deferred','escalate','stop','running'}:reason='Task execution is held or already running'
    return {'eligible':reason is None,'reason':reason,'decision':resolution}


def capsule(store,run,adapter):
    import fcntl
    with (store.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _capsule(store,run,adapter)


def dispatch(engine,handoff,task_id,option=None):
    """One durable inference delivery per capsule; imports can resume without regeneration."""
    import fcntl
    store=engine.store
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        row=store.db.execute('SELECT body FROM handoffs WHERE id=?',(handoff,)).fetchone()
        if not row:raise ValueError('Unknown handoff')
        body=json.loads(row[0]);run=body['run']
        if body['schema'] not in {'precedent-handoff/3','precedent-handoff/4','precedent-handoff/5'}:raise ValueError('A new handoff with frozen context is required')
        task=next((t for t in body['tasks'] if t['id']==task_id),None)
        if not task or task_id not in body['contexts']:raise ValueError('Task is not eligible in this handoff')
        options=task.get('options',['Implement the requirement'])
        if option is None and len(options)==1:option=options[0]
        if option not in options:raise ValueError('Choose an exact alternative')
        prior=store.db.execute('SELECT body FROM deliveries WHERE id=?',(handoff,)).fetchone()
        if prior:
            delivery=json.loads(prior[0])
            if delivery['task']!=task_id or delivery['option']!=option:raise ValueError('Handoff already delivered for a different task or alternative')
            if delivery.get('result'):return delivery['result']
            if not delivery.get('response'):return {'run':run,'state':'interrupted','reason':'Delivery outcome uncertain; no automatic regeneration'}
        else:
            engine.check_main(run);state=store.run(run)
            for field,actual in [('tasks',state['tasks']),('decisions',state['decisions']),('policies',state['rule_snapshot'])]:
                if body[field]!=actual:raise ValueError('Handoff scope changed: '+field)
            if state.get('task_rule_snapshots',{})!=body.get('task_rule_snapshots',{}):raise ValueError('Handoff task judgments changed')
            check_dependency_snapshot(store,body,task)
            allowed=handoff_eligibility(state,task)
            if not allowed['eligible']:raise ValueError(allowed['reason'])
            if len(store.candidates(run))>=state['limits']['max_total_candidates']:raise ValueError('Candidate budget exhausted')
            adapter=body['adapter']['id'];require_inference(adapter)
            from .capabilities import require_compatible
            require_compatible(adapter,state.get('local_model',''))
            delivery={'run':run,'task':task_id,'option':option,'adapter':adapter,'state':'sending'}
            store.db.execute('INSERT INTO deliveries VALUES(?,?)',(handoff,encode(delivery)));store.db.commit()
            store.event('handoff_dispatch_started',{'handoff':handoff,**delivery})
            try:
                prompt='Implement this one authorized alternative using the frozen context. Return JSON {"files":{"relative/path":"complete replacement source"}} only. Edit only these paths: '+encode(task['editable'])+'. Dependency files outside that list are read-only. No tools. Never edit tests. Requirement: '+task['requirement']+'\nAlternative: '+option+'\nContext: '+encode(body['contexts'][task_id])
                answer=engine.model(run,'ollama',prompt,owner='delivery:'+handoff,adapter=adapter)
                if not isinstance(answer,dict) or not isinstance(answer.get('files'),dict):raise ValueError('Delivery returned no files object')
                response={'schema':'precedent-response/1','handoff':handoff,'base':body['base'],'task':task_id,'option':option,'files':answer['files']}
                path=store.home/'handoffs'/(handoff+'-response.json');path.write_text(encode(response))
                delivery.update({'state':'received','response':str(path),'response_digest':sha(encode(response))})
            except Exception as error:
                delivery.update({'state':'interrupted','error':str(error)})
            store.db.execute('UPDATE deliveries SET body=? WHERE id=?',(encode(delivery),handoff));store.db.commit()
            store.event('handoff_dispatch_received',{'handoff':handoff,**delivery})
            if not delivery.get('response'):return {'run':run,'state':'interrupted','error':delivery['error']}
    # Import takes the same execution lock, after delivery releases it.
    path=Path(delivery['response'])
    if sha(encode(json.loads(path.read_text())))!=delivery['response_digest']:raise ValueError('Saved delivery response changed')
    result=import_response(engine,path)
    delivery['result']=result;delivery['state']='checked'
    store.db.execute('UPDATE deliveries SET body=? WHERE id=?',(encode(delivery),handoff));store.db.commit()
    return result
