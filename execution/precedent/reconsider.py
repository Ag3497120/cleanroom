"""Apply newly registered policy to a held, unbuilt task by explicit operator action."""
from .policy import decide

def task_rules(state,task_id):return state.get('task_rule_snapshots',{}).get(task_id,state['rule_snapshot'])

def reconsider(engine,run,task_id):
    import fcntl
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=engine.store.run(run)
        if not state:raise ValueError('Unknown run')
        task=next((t for t in state['tasks'] if t['id']==task_id),None)
        if not task or state['status'].get(task_id) not in {'defer','deferred','escalate'}:raise ValueError('Only a held task can adopt a new judgment')
        if state.get('stopped'):raise ValueError('Stopped runs cannot be reconsidered')
        if any(c['task']==task_id for c in engine.store.candidates(run)):raise ValueError('Existing candidates retain their original judgment; this operation requires no candidates')
        engine.check_main(run)
        latest=engine.store.rules();previous=task_rules(state,task_id)
        decision=decide(latest,state['repository'],task['event'],task.get('facts',{}),task.get('evidence',{}))
        state.setdefault('task_rule_snapshots',{})[task_id]=latest;state['decisions'][task_id]=decision
        state['status'][task_id]='pending' if decision['action'] in {'APPLY','STAGE','FORK'} else decision['action'].lower()
        if decision['action']=='STOP':state['stopped']=True
        engine.store.run(run,state);engine.emit(run,'task_judgment_reconsidered',{'task':task_id,'previous_rules':previous,'new_rules':latest,'decision':decision,'execution_started':False});engine.bundle(run)
        return {'run':run,'task':task_id,'state':state['status'][task_id],'decision':decision,'execution_started':False}
