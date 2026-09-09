import datetime as dt
import fnmatch

ACTIONS={'APPLY','STAGE','FORK','DEFER','ESCALATE','STOP'}
EVENTS={'PUBLIC_API_CHANGE','NEW_DEPENDENCY','TEST_SPEC_CONFLICT','AMBIGUOUS_REQUIREMENT','PERFORMANCE_REGRESSION','SECURITY_SCOPE_EXPANSION','HUMAN_EDIT_CONFLICT','FAILED_VERIFICATION','NO_SEPARATING_SIGNAL','IRREVERSIBLE_ACTION'}
STATES={'DRAFT','SHADOW','CONFIRMED','ACTIVE','RETIRED'}

def validate(rule):
    required={'id','scope','when','action','evidence_required','exceptions','expires','examples','counterexamples','status','version'}
    if not isinstance(rule,dict) or not required<=rule.keys():raise ValueError('Rule fields missing')
    if not isinstance(rule['id'],str) or not rule['id']:raise ValueError('Rule ID required')
    if rule['action'] not in ACTIONS or rule['status'] not in STATES:raise ValueError('Unknown action/state')
    if type(rule['version']) is not int or rule['version']<1:raise ValueError('Positive version required')
    if not isinstance(rule['scope'],dict) or rule['scope'].get('event') not in EVENTS or not isinstance(rule['scope'].get('repository'),str):raise ValueError('Explicit scope required')
    if not isinstance(rule['when'],dict) or not isinstance(rule['exceptions'],list):raise ValueError('Conditions must be structured')
    for conditions in [rule['when'],*rule['exceptions']]:
        if not isinstance(conditions,dict) or any(not isinstance(k,str) or not isinstance(v,(str,bool,int,float,type(None))) for k,v in conditions.items()):raise ValueError('Only literal equality conditions allowed')
    for key in ('evidence_required','examples','counterexamples'):
        if not isinstance(rule[key],list) or any(not isinstance(v,str) for v in rule[key]):raise ValueError('Expected string list: '+key)
    if rule['expires'] is not None:dt.datetime.fromisoformat(rule['expires']).astimezone(dt.timezone.utc)
    return rule

def match(conditions,facts):
    if any(k not in facts for k in conditions):return None
    return all(type(facts[k]) is type(v) and facts[k]==v for k,v in conditions.items())

def decide(rules,repository,event,facts,evidence):
    if event not in EVENTS:raise ValueError('Unknown decision event')
    if event in {'IRREVERSIBLE_ACTION','SECURITY_SCOPE_EXPANSION'}:
        return {'action':'ESCALATE','reason':'Authority boundary requires explicit operator action','rules':[],'shadow':[]}
    matches=[];unknown=[];shadow=[];shadow_unknown=[]
    for rule in rules:
        validate(rule)
        if rule['status'] not in {'ACTIVE','SHADOW'}:continue
        if rule['scope']['event']!=event or not fnmatch.fnmatchcase(repository,rule['scope']['repository']):continue
        if rule['expires'] and dt.datetime.fromisoformat(rule['expires']).astimezone(dt.timezone.utc)<=dt.datetime.now(dt.timezone.utc):continue
        hit=match(rule['when'],facts)
        exceptions=[match(x,facts) for x in rule['exceptions']]
        if hit is False or True in exceptions:continue
        if hit is None or None in exceptions or any(not evidence.get(k) for k in rule['evidence_required']):
            if rule['status']=='SHADOW':shadow_unknown.append({'id':rule['id'],'action':'DEFER','proposed_action':rule['action'],'reason':'Missing evidence or unknown predicate in shadow evaluation'})
            else:unknown.append(rule['id'])
            continue
        (shadow if rule['status']=='SHADOW' else matches).append(rule)
    predictions=[{'id':r['id'],'action':r['action']} for r in shadow]+shadow_unknown
    if unknown:return {'action':'DEFER','reason':'Missing evidence or unknown predicate','rules':unknown,'shadow':predictions}
    if not matches:return {'action':'ESCALATE','reason':'No active applicable rule','rules':[],'shadow':predictions}
    actions={r['action'] for r in matches}
    if len(actions)>1:return {'action':'ESCALATE','reason':'Conflicting active rules','rules':[r['id'] for r in matches],'shadow':predictions}
    return {'action':matches[0]['action'],'reason':'Confirmed scoped precedent','rules':[{'id':r['id'],'version':r['version']} for r in matches],'shadow':predictions}
