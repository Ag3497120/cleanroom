"""Opt-in, bounded routing before a call; never retries an uncertain delivery."""
from .transport_health import LOCAL,recommendations

ROLES={'builder','test_designer','reviewer'}

def configure(engine,run,rules):
    import fcntl
    from .adapters import require_inference
    if not isinstance(rules,dict) or set(rules)-ROLES:raise ValueError('Routing rules must map known roles to settings')
    with (engine.home/'execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=engine.store.run(run)
        if not state:raise ValueError('Unknown run')
        checked={}
        for role,rule in rules.items():
            if not isinstance(rule,dict) or set(rule)-{'allowed','min_valid_responses','max_switches'}:raise ValueError('Unknown routing setting')
            allowed=rule.get('allowed');minimum=rule.get('min_valid_responses',2);maximum=rule.get('max_switches',2)
            if not isinstance(allowed,list) or not allowed or not all(isinstance(x,str) for x in allowed) or len(set(allowed))!=len(allowed):raise ValueError('Distinct allowed adapter IDs required')
            if type(minimum) is not int or not 1<=minimum<=20 or type(maximum) is not int or not 1<=maximum<=10:raise ValueError('Routing bounds: 1..20 valid responses, 1..10 switches')
            current=state.get('bindings',{}).get(role,'ollama' if role=='builder' else 'claude-cli')
            if current not in allowed:raise ValueError('Include the current adapter in the allowed set')
            for adapter in allowed:
                require_inference(adapter)
                from .capabilities import require_compatible
                require_compatible(adapter,state['local_model'])
                if (adapter in LOCAL)!=(current in LOCAL):raise ValueError('Automatic routing cannot cross local/cloud budgets')
            checked[role]={'allowed':allowed,'min_valid_responses':minimum,'max_switches':maximum}
        state['routing']={'version':state.get('routing',{}).get('version',0)+1,'rules':checked}
        engine.store.run(run,state);engine.emit(run,'routing_configured',{'routing':state['routing'],'source':'operator','usage_preserved':state['usage']})
        return state['routing']

def choose(engine,run,role,current):
    state=engine.store.run(run);policy=state.get('routing',{});rule=policy.get('rules',{}).get(role)
    if not rule or current not in rule['allowed']:return current
    history=state.get('routing_switches',[])
    if sum(x['role']==role for x in history)>=rule['max_switches']:return current
    report=recommendations(engine.store,run,role)
    prior=next((x for x in report['alternatives'] if x['adapter']==current),None)
    if not prior or prior['last_outcome'] not in {'transport_error','json_error','contract_error'}:return current
    best=None
    from .capabilities import require_compatible
    for candidate in report['alternatives']:
        if candidate['adapter'] not in rule['allowed'] or candidate['valid_responses']<rule['min_valid_responses'] or candidate['score']<=prior['score']:continue
        try:require_compatible(candidate['adapter'],state['local_model'])
        except ValueError:continue
        best=candidate;break
    if not best:return current
    # No inference is performed here. The caller still charges its existing budget once.
    transition={'role':role,'old':current,'new':best['adapter'],'policy_version':policy['version'],'reason':'Recent response failure; allowed alternative has observed valid responses','evidence':{'old':prior,'new':best}}
    state.setdefault('bindings',{})[role]=best['adapter'];state.setdefault('routing_switches',[]).append(transition)
    engine.store.run(run,state);engine.emit(run,'adapter_auto_replaced',transition)
    return best['adapter']
