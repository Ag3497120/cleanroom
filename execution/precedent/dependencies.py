"""Explicit candidate composition; never guesses between verified alternatives."""
from .reconsider import task_rules
import json,time
from pathlib import Path
from .store import encode,sha
from .execution import run_tests

def context(engine,run,task):
    state=engine.store.run(run)
    binding=state.get('dependency_bindings',{}).get(task['id'])
    if not binding:return {},[]
    files={};checks=[]
    for key in binding['candidates'].values():
        item=engine.store.candidate(key)
        if not item or item not in engine.store.candidates(run) or item['state']!='verified':raise ValueError('Dependency is no longer verified')
        engine._check_candidate_files(run,item)
        if item['source_digest']!=binding['digests'][key]:raise ValueError('Dependency selection changed')
        for name,value in item['files'].items():
            if name in files and files[name]!=value:raise ValueError('Conflicting dependency files: '+name)
            files[name]=value
        checks.extend(item.get('dependency_checks',[]))
        parent=next(t for t in state['tasks'] if t['id']==item['task'])
        folder=engine.home/'runs'/run
        from .harness_audit import checked_harness
        harness=checked_harness(folder,parent['id'],item.get('harness_digest'))
        audits=[json.loads(row[0]) for row in engine.store.db.execute("SELECT body FROM ledger WHERE kind='harness_audit'")]
        if not harness or not any(a.get('run')==run and a.get('task')==parent['id'] and a.get('digest')==item['harness_digest'] and a.get('audit',{}).get('verdict')=='PASS' for a in audits):raise ValueError('Dependency harness missing or unaudited')
        checks.append({'candidate':key,'tests':parent['tests'],'harness':str(harness),'digest':item['harness_digest']})
    if len(encode(files).encode())>state['limits']['max_source_bytes']:raise ValueError('Dependency source budget exceeded')
    return files,list({c['candidate']:c for c in checks}.values())

def test_dependencies(tree,checks):
    reports=[]
    for check in checks:
        harness=Path(check['harness'])
        if not harness.is_file() or sha(harness.read_bytes())!=check['digest']:raise ValueError('Dependency harness changed')
        from .harness_audit import assert_harness_logic
        assert_harness_logic(harness.read_text())
        report=run_tests(tree,[*[tree/p for p in check['tests']],harness])
        reports.append({'candidate':check['candidate'],**report})
    return reports

def bind(engine,run,task_id,selections):
    import fcntl
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=engine.store.run(run);engine.check_main(run)
        task=next((t for t in state['tasks'] if t['id']==task_id),None)
        if not task or not task.get('depends_on'):raise ValueError('Task has no dependencies')
        if state.get('stopped') or time.time()>state['deadline']:raise ValueError('Execution is stopped or expired')
        if not isinstance(selections,dict) or set(selections)!=set(task['depends_on']):raise ValueError('Select exactly one candidate for each dependency')
        if any(c['task']==task_id for c in engine.store.candidates(run)):raise ValueError('Task already has candidates; selection is frozen')
        digests={}
        for parent,key in selections.items():
            item=engine.store.candidate(key)
            if not item or item not in engine.store.candidates(run) or item['task']!=parent or item['state']!='verified':raise ValueError('Select a verified candidate belonging to each dependency')
            digests[key]=item['source_digest']
        binding={'candidates':selections,'digests':digests}
        previous=state.get('dependency_bindings',{}).get(task_id)
        state.setdefault('dependency_bindings',{})[task_id]=binding
        engine.store.run(run,state)
        try:context(engine,run,task)
        except Exception:
            if previous is None:state['dependency_bindings'].pop(task_id)
            else:state['dependency_bindings'][task_id]=previous
            engine.store.run(run,state);raise
        from .policy import decide
        decision=decide(task_rules(state,task['id']),state['repository'],task['event'],task.get('facts',{}),task.get('evidence',{}))
        state['decisions'][task_id]=decision
        state['status'][task_id]='pending' if decision['action'] in {'APPLY','STAGE','FORK'} else decision['action'].lower()
        engine.store.run(run,state)
        engine.emit(run,'dependencies_selected',{'task':task_id,**binding});engine.bundle(run)
        return {'run':run,'task':task_id,**binding,'execution_started':False}
