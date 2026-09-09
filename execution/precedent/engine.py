from .reconsider import task_rules
import ast,json,os,re,time,uuid
from pathlib import Path
from .store import Store,encode,sha
from .policy import decide,validate
from .execution import git,safe_path,apply_files,run_tests
from .models import invoke,object_response,ModelResponseError
from .detector import detect

DEFAULT_LIMITS={'max_candidates':2,'max_total_candidates':6,'local_calls':8,'cloud_calls':7,'seconds':900,'max_diff_bytes':50000,'max_source_bytes':24000,'max_worktree_bytes':20000000,'cloud_top_k':2}

def repair_feedback(item,max_source_bytes):
    """Retain full evidence in the candidate, but bound source replay to the model."""
    syntax=dict(item['syntax_failure']) if item.get('syntax_failure') else None
    feedback={'candidate':item['id'],'error':item.get('error'),'public':item.get('public'),'prior_files':item.get('files'),'syntax_failure':syntax}
    source={'prior_files':feedback['prior_files'],'syntax_source':syntax.get('source') if syntax else None}
    encoded=encode(source)
    if len(encoded.encode())>max_source_bytes:
        feedback['prior_files']=None
        if syntax:syntax.pop('source',None)
        feedback['source_omitted']={'reason':'Prior source exceeds the repair context budget; reconstruct from the original task and reported error','digest':sha(encoded),'bytes':len(encoded.encode())}
    return feedback


def compile_precedent(text,model='qwen2.5:3b'):
    schema={'id':'short-id','scope':{'repository':'explicit repo path or *','event':'NEW_DEPENDENCY'},'when':{},'action':'FORK','evidence_required':[],'exceptions':[],'expires':None,'examples':['example'],'counterexamples':['counterexample'],'status':'DRAFT','version':1}
    prompt='Translate the user preference into exactly one JSON decision rule. Never activate a rule. Allowed event names: PUBLIC_API_CHANGE NEW_DEPENDENCY TEST_SPEC_CONFLICT AMBIGUOUS_REQUIREMENT PERFORMANCE_REGRESSION SECURITY_SCOPE_EXPANSION HUMAN_EDIT_CONFLICT FAILED_VERIFICATION NO_SEPARATING_SIGNAL IRREVERSIBLE_ACTION. Allowed actions: APPLY STAGE FORK DEFER ESCALATE STOP. Conditions are literal equality objects; never code. Preserve user scope; if unspecified use * for a draft that requires explicit confirmation. Required schema: '+encode(schema)+'\nUser preference:\n'+text
    result,usage=invoke({'provider':'ollama','model':model},prompt)
    rule=object_response(result);rule['status']='DRAFT';rule['version']=1;validate(rule)
    return rule,usage

class Engine:
    def __init__(self,home):self.store=Store(home);self.home=self.store.home
    def emit(self,run,event,body):self.store.event(event,{'run':run,**body})
    def renew_window(self,run,seconds,expected_deadline):
        """Explicit operator action: renew elapsed wall time, never inference/candidate budgets."""
        import fcntl
        with (self.home/'execution.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            state=self.store.run(run)
            if not state:raise ValueError('Unknown run')
            if type(seconds) is not int or not 0<seconds<=state['limits']['seconds']:raise ValueError('Window must fit the original per-window time limit')
            if state['deadline']!=expected_deadline:raise ValueError('Execution window changed; refresh before renewing')
            if state.get('stopped'):raise ValueError('Stopped execution cannot be renewed')
            now=time.time()
            if now<=state['deadline']:raise ValueError('Execution window is still active')
            if all(state['usage'][k]>=state['limits'][k] for k in ('local_calls','cloud_calls')):raise ValueError('No inference budget remains')
            self.check_main(run)
            window={'opened_at':now,'expires_at':now+seconds,'previous_deadline':state['deadline'],'source':'operator','seconds':seconds}
            state.setdefault('execution_windows',[]).append(window);state['deadline']=window['expires_at'];self.store.run(run,state)
            self.emit(run,'execution_window_renewed',{**window,'usage_preserved':state['usage'],'limits_preserved':state['limits']})
            self.bundle(run)
            return {'run':run,'deadline':state['deadline'],'seconds':seconds,'remaining_calls':{k:state['limits'][k]-state['usage'][k] for k in ('local_calls','cloud_calls')},'execution_started':False}
    def model(self,run,provider,prompt,owner=None,adapter=None,profile_options=None):
        self.store.assert_ledger()
        body=self.store.run(run)
        role='builder' if provider=='ollama' else ('test_designer' if owner and owner.startswith(('task:','harness:')) else 'reviewer')
        provider=adapter if adapter is not None else body.get('bindings',{}).get(role,provider)
        from .adapters import require_inference
        initial_key='local_calls' if provider in {'ollama','pi','opencode','openclaw','hermes'} else 'cloud_calls'
        if body.get('stopped') or body['usage'][initial_key]>=body['limits'][initial_key] or time.time()>body['deadline']:raise RuntimeError('Execution stopped or inference budget exhausted')
        if adapter is None and not body.get('stopped'):
            from .routing import choose
            provider=choose(self,run,role,provider);body=self.store.run(run)
        require_inference(provider)
        from .capabilities import require_compatible
        require_compatible(provider,body['local_model'])
        key='local_calls' if provider in {'ollama','pi','opencode','openclaw','hermes'} else 'cloud_calls'
        if body['usage'][key]>=body['limits'][key] or time.time()>body['deadline']:raise RuntimeError('Inference budget exhausted')
        from .profiles import active,validate
        settings=None
        if profile_options is not None and provider!='ollama':raise ValueError('Runtime profiles currently support Ollama only')
        if provider=='ollama':settings=validate(profile_options) if profile_options is not None else active(self.store,body['local_model'])
        if time.time()>body['deadline']:raise ValueError('Execution expired during profile verification')
        body['usage'][key]+=1;self.store.run(run,body)
        from .transport_health import contract,response_schema
        requested_model=body['local_model'] if key=='local_calls' else 'configured-default'
        started=time.monotonic();stage='transport_error';usage=None
        try:
            binding={'provider':provider,'model':requested_model}
            if settings is not None:binding['options']=settings
            if provider=='claude-cli':binding['response_schema']=response_schema(role,owner)
            text,usage=invoke(binding,prompt)
            body=self.store.run(run);body['usage']['tokens_observed']+=usage['tokens'] or 0;body['usage']['model_seconds']+=usage['elapsed_seconds'];self.store.run(run,body)
            self.emit(run,'model_call',{**usage,'owner':owner,**({'profile_options':settings} if settings else {})})
            stage='json_error';result=object_response(text)
            stage='contract_error';result=contract(result,role,owner)
            stage='valid_response';return result
        except Exception as error:
            if usage is None and isinstance(error,ModelResponseError):
                usage=error.usage;body=self.store.run(run);body['usage']['tokens_observed']+=usage['tokens'] or 0;body['usage']['model_seconds']+=usage['elapsed_seconds'];self.store.run(run,body)
                self.emit(run,'model_call',{**usage,'owner':owner,'response_rejected':True,**({'profile_options':settings} if settings else {})})
            self.emit(run,'model_failure',{'provider':provider,'error':str(error),'tokens':usage.get('tokens') if usage else None});raise
        finally:
            self.emit(run,'transport_observation',{'provider':provider,'role':role,'owner':owner,'requested_model':requested_model,'observed_model':usage.get('model') if usage else None,'outcome':stage,**({'done_reason':usage['done_reason']} if usage and 'done_reason' in usage else {}),'seconds':time.monotonic()-started,'tokens':usage.get('tokens') if usage else None})
    def create(self,manifest):
        self.store.assert_ledger()
        repo=Path(manifest['repository']).resolve()
        if git(repo,'status','--porcelain'):raise ValueError('Target repository must be clean before creating candidates')
        head=git(repo,'rev-parse','HEAD');tasks=manifest['tasks'];ids={t['id'] for t in tasks}
        if len(ids)!=len(tasks):raise ValueError('Duplicate task ID')
        for task in tasks:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',task['id']):raise ValueError('Invalid task ID')
            if not set(task.get('depends_on',[]))<=ids:raise ValueError('Unknown dependency')
            for name in task['editable']:safe_path(repo,name)
            for name in task['tests']:
                path=safe_path(repo,name)
                if not path.is_file() or name in task['editable']:raise ValueError('Tests must exist and remain frozen')
        frozen={p for t in tasks for p in t['tests']}
        if any(set(t['editable']) & frozen for t in tasks):raise ValueError('A task cannot edit any frozen test in the run')
        pending=set(ids);done=set()
        while pending:
            ready={t['id'] for t in tasks if t['id'] in pending and set(t.get('depends_on',[]))<=done}
            if not ready:raise ValueError('Dependency cycle')
            done|=ready;pending-=ready
        key=uuid.uuid4().hex[:12];limits={**DEFAULT_LIMITS,**manifest.get('limits',{})}
        if any(type(v) is not int or v<=0 for v in limits.values()):raise ValueError('Positive integer limits required')
        body={'id':key,'repository':str(repo),'base':head,'tasks':tasks,'status':{t['id']:'pending' for t in tasks},'decisions':{},'local_model':manifest.get('local_model','qwen2.5:3b'),'limits':limits,'usage':{'local_calls':0,'cloud_calls':0,'tokens_observed':0,'model_seconds':0},'deadline':time.time()+limits['seconds'],'created':time.time(),'bindings':manifest.get('bindings',{}),'rule_snapshot':self.store.rules(),'test_hashes':{name:sha((repo/name).read_bytes()) for t in tasks for name in t['tests']}}
        from .adapters import require_inference
        for role,adapter in body['bindings'].items():
            if role not in {'builder','test_designer','reviewer'}:raise ValueError('Unknown adapter role')
            require_inference(adapter)
            from .capabilities import require_compatible
            require_compatible(adapter,body['local_model'])
        self.store.run(key,body);self.emit(key,'created',{'base':head,'rule_versions':[{k:r[k] for k in ('id','version','status')} for r in body['rule_snapshot']]});return key
    def check_main(self,run):
        self.store.assert_ledger()
        body=self.store.run(run);repo=Path(body['repository'])
        if git(repo,'rev-parse','HEAD')!=body['base'] or git(repo,'status','--porcelain'):raise RuntimeError('HUMAN_EDIT_CONFLICT: target changed; candidates retained, no overwrite')
    def execute(self,run):
        self.store.assert_ledger()
        import fcntl
        with (self.home/'execution.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            state=self.store.run(run)
            if not state:raise ValueError('Unknown run')
            if not state.get('stopped') and 'pending' in state['status'].values() and time.time()>state['deadline']:raise ValueError('Execution window expired; pending tasks were preserved')
            return self._execute(run)
    def _execute(self,run):
        body=self.store.run(run)
        if body.get('stopped'):return body
        # Interrupted work is uncertain, never silently repeated or counted complete.
        for key,status in body['status'].items():
            if status=='running':body['status'][key]='deferred';body['decisions'][key]={'action':'DEFER','reason':'Interrupted execution; inspect existing candidates before retry'}
        self.store.run(run,body)
        for task in body['tasks']:
            current=self.store.run(run)
            if current['status'][task['id']]!='pending':continue
            if task.get('depends_on') and task['id'] not in current.get('dependency_bindings',{}):
                current['status'][task['id']]='deferred';current['decisions'][task['id']]={'action':'DEFER','reason':'Dependency requires an explicit combined baseline; independent tasks continue'};self.store.run(run,current);continue
            decision=decide(task_rules(current,task['id']),current['repository'],task['event'],task.get('facts',{}),task.get('evidence',{}))
            current['decisions'][task['id']]=decision
            self.emit(run,'decision',{'task':task['id'],**decision})
            action=decision['action']
            if action in {'DEFER','ESCALATE','STOP'}:
                current['status'][task['id']]=action.lower();self.store.run(run,current)
                if action=='STOP':
                    current['stopped']=True;self.store.run(run,current);break
                continue
            current['status'][task['id']]='running';self.store.run(run,current)
            try:
                self.check_main(run);ready=self.build_task(run,task,action)
                current=self.store.run(run)
                if current['status'][task['id']]=='running':current['status'][task['id']]='ready' if ready else 'failed'
                self.store.run(run,current)
                if current.get('stopped'):break
            except Exception as error:
                current=self.store.run(run);current['status'][task['id']]='deferred';current['decisions'][task['id']]['execution_error']=str(error);self.store.run(run,current);self.emit(run,'execution_failure',{'task':task['id'],'error':str(error)})
        try:self.check_main(run)
        except Exception as error:
            current=self.store.run(run);current['human_edit_conflict']=str(error);self.store.run(run,current);self.emit(run,'human_edit_conflict',{'error':str(error)})
        self.bundle(run);return self.store.run(run)
    def build_task(self,run,task,action,incoming=None):
        body=self.store.run(run);repo=Path(body['repository']);base=body['base']
        from .capabilities import require_compatible
        roles=['test_designer','reviewer']+([] if incoming else ['builder'])
        for role in roles:require_compatible(body.get('bindings',{}).get(role,'ollama' if role=='builder' else 'claude-cli'),body['local_model'])
        from .dependencies import context,test_dependencies
        inherited,dependency_checks=context(self,run,task)
        source={p:inherited.get(p,git(repo,'show',base+':'+p) if (repo/p).exists() else '') for p in task['editable']}
        if len(encode({'editable':source,'dependencies':inherited}).encode())>body['limits']['max_source_bytes']:raise ValueError('Source context budget exceeded')
        tests={p:(repo/p).read_text() for p in task['tests']}
        # Test design happens before any candidate and sees no Builder explanation.
        designed=self.model(run,'claude-cli','Return JSON {"tests":"complete Python unittest code"}. Design independent additional tests of this requirement. Import the target module directly; unittest classes only. No tools, filesystem/network/subprocess operations, no external packages. Do not weaken the requirement. Requirement:\n'+task['requirement']+'\nPublic tests:\n'+encode(tests)+'\nEditable module names:\n'+encode(task['editable']),owner='task:'+task['id'])
        test_source=designed['tests'];compile(test_source,'cloud-tests','exec')
        tree=ast.parse(test_source)
        if not any(isinstance(n,ast.FunctionDef) and n.name.startswith('test_') for n in ast.walk(tree)):raise ValueError('Cloud harness contains no tests')
        folder=self.home/'runs'/run;folder.mkdir(parents=True,exist_ok=True)
        harness=folder/(task['id']+'-'+uuid.uuid4().hex[:8]+'-frozen-tests.py');harness.write_text(test_source);harness.chmod(0o400)
        self.emit(run,'harness_frozen',{'task':task['id'],'digest':sha(test_source)})
        from .harness_audit import audit_prompt,assert_harness_logic
        assert_harness_logic(test_source)
        audit=self.model(run,'claude-cli',audit_prompt(task['requirement'],test_source),owner='harness:'+task['id'])
        self.emit(run,'harness_audit',{'task':task['id'],'digest':sha(test_source),'audit':audit})
        if audit.get('verdict')!='PASS':raise RuntimeError('CONTESTED_TEST: frozen harness needs operator review: '+encode(audit))
        options=[incoming['option']] if incoming else task.get('options',['Implement the requirement'])
        options=options[:body['limits']['max_candidates']] if action=='FORK' else options[:1]
        local_pass=[];seen=set()
        planned=[(option,0,None) for option in options]
        for index,(option,attempt,feedback) in enumerate(planned):
            if len(self.store.candidates(run))>=body['limits']['max_total_candidates']:break
            key=uuid.uuid4().hex[:12];worktree=self.home/'trees'/key;worktree.parent.mkdir(exist_ok=True)
            branch='precedent/'+run+'/'+key
            git(repo,'worktree','add','-b',branch,str(worktree),base)
            item={'id':key,'task':task['id'],'option':option,'branch':branch,'worktree':str(worktree),'state':'building','base':base,'patch':None,'cloud':None,'attempt':attempt}
            if feedback and feedback.get('candidate'):item['repair_of']=feedback['candidate']
            if incoming:item['handoff']=incoming['handoff'];item['origin']=incoming.get('_origin','operator_supplied_unverified')
            self.store.candidate(key,run,item)
            try:
                answer={'files':incoming['files']} if incoming else self.model(run,'ollama','You implement a coding alternative. Return JSON {"files":{"relative/path":"complete replacement content"}} and nothing else. Include every import and helper needed: each value replaces the ENTIRE file, not just a function. Only edit the listed files; never change tests. Standard library only unless explicitly allowed. Requirement:\n'+task['requirement']+'\nAlternative:\n'+option+'\nCurrent files:\n'+encode(source)+'\nRead-only dependency files:\n'+encode(inherited)+'\nPublic tests:\n'+encode(tests)+'\nPrior public-only failure, if any:\n'+encode(feedback),owner='candidate:'+key)
                if inherited:apply_files(worktree,inherited,list(inherited))
                try:apply_files(worktree,answer['files'],task['editable'])
                except SyntaxError as error:
                    item['syntax_failure']={'file':error.filename,'line':error.lineno,'message':error.msg,'source':answer['files'][error.filename]}
                    raise
                size=sum(p.stat().st_size for p in worktree.rglob('*') if p.is_file() and not p.is_symlink())
                if size>body['limits']['max_worktree_bytes']:raise ValueError('Worktree storage quota')
                item['files']={**inherited,**answer['files']};item['source_digest']=sha(encode(item['files']));item['dependency_checks']=dependency_checks
                item['detected_decisions']=[]
                for observed in detect(source,answer['files']):
                    resolution=decide(task_rules(body,task['id']),body['repository'],observed['event'],observed['facts'],observed['evidence'])
                    item['detected_decisions'].append({**observed,'resolution':resolution})
                    self.emit(run,'detected_decision',{'candidate':key,**observed,'resolution':resolution})
                    if resolution['action']!='APPLY':raise ValueError('New decision in generated diff requires review: '+observed['event'])
                if item['source_digest'] in seen:item['state']='duplicate';self.store.candidate(key,run,item);continue
                seen.add(item['source_digest'])
                for name in task['tests']:
                    if sha((worktree/name).read_bytes())!=body['test_hashes'][name]:raise ValueError('Frozen test modified')
                patch=''
                for name in answer['files']:
                    import difflib
                    diff=list(difflib.unified_diff(source[name].splitlines(True),answer['files'][name].splitlines(True),fromfile='a/'+name if (repo/name).exists() else '/dev/null',tofile='b/'+name))
                    patch+=''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in diff)
                if len(patch.encode())>body['limits']['max_diff_bytes']:raise ValueError('Diff budget exceeded')
                item['task_patch']=patch
                if inherited:
                    patch=''
                    for name,value in item['files'].items():
                        old=git(repo,'show',base+':'+name) if (repo/name).exists() else ''
                        diff=difflib.unified_diff(old.splitlines(True),value.splitlines(True),fromfile='a/'+name if (repo/name).exists() else '/dev/null',tofile='b/'+name)
                        patch+=''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in diff)
                    if len(patch.encode())>body['limits']['max_diff_bytes']:raise ValueError('Combined diff budget exceeded')
                item['patch']=patch;item['changed_lines']=sum(1 for l in patch.splitlines() if l.startswith(('+','-')) and not l.startswith(('+++','---')))
                public=run_tests(worktree,[worktree/p for p in task['tests']]);holdout=run_tests(worktree,[harness]) if public['passed'] else None
                item['public']=public;item['holdout']=holdout;item['harness_digest']=sha(test_source);item['harness_path']=str(harness)
                after={name:(worktree/name).read_text() for name in answer['files']}
                if after!=answer['files']:raise ValueError('Candidate changed while testing')
                item['dependency_reports']=test_dependencies(worktree,dependency_checks) if public['passed'] and holdout and holdout['passed'] else []
                dependencies_pass=all(r['passed'] for r in item['dependency_reports'])
                item['state']='tested' if public['passed'] and holdout and holdout['passed'] and dependencies_pass else 'rejected'
                if item['state']=='tested':local_pass.append(item)

            except Exception as error:item['state']='rejected';item['error']=str(error)
            self.store.candidate(key,run,item);self.emit(run,'candidate_tested',{'candidate':key,'state':item['state']})
            if item['state']=='rejected':
                facts={'tests_failed':any(report and not report.get('passed') for report in [item.get('public'),item.get('holdout'),*item.get('dependency_reports',[])]),'syntax_failed':bool(item.get('syntax_failure'))}
                evidence={'test_reports':bool(item.get('public') or item.get('holdout')),'compiler_report':bool(item.get('syntax_failure'))}
                if self._apply_failure_decision(run,task,item,{**facts,'review_failed':False,'review_unknown':False,'review_error':False},evidence):return []
            if not incoming and item['state']=='rejected' and attempt<1 and (item.get('error') or not item.get('public',{}).get('passed',False)):
                planned.append((option,attempt+1,repair_feedback(item,body['limits']['max_source_bytes'])))
        ready=[]
        for item in sorted(local_pass,key=lambda x:x['changed_lines'])[:body['limits']['cloud_top_k']]:
            self._review(run,task,item,source)
            if self.store.run(run)['status'][task['id']] in {'defer','escalate','stop'}:return []
            if item['state']=='verified':ready.append(item['id'])
        return ready
    def _apply_failure_decision(self,run,task,item,facts,evidence):
        state=self.store.run(run)
        resolution=decide(task_rules(state,task['id']),state['repository'],'FAILED_VERIFICATION',facts,evidence)
        item['failure_decision']=resolution;self.store.candidate(item['id'],run,item)
        self.emit(run,'detected_decision',{'candidate':item['id'],'event':'FAILED_VERIFICATION','resolution':resolution})
        if not resolution['rules'] or resolution['action'] not in {'DEFER','ESCALATE','STOP'}:return False
        state['status'][task['id']]=resolution['action'].lower();state['decisions'][task['id']]=resolution
        state.setdefault('failure_decisions',{})[task['id']]=resolution
        if resolution['action']=='STOP':state['stopped']=True
        self.store.run(run,state);return True
    def _review(self,run,task,item,source):
        item['state']='reviewing';self.store.candidate(item['id'],run,item)
        try:
            verdict=self.model(run,'claude-cli','Independently review this code change. Return JSON {"verdict":"PASS or FAIL or UNKNOWN","findings":["..."]}. Do not infer correctness from the builder; no builder explanation is supplied. No tools. Flag contract violations and hard-coded answers. Requirement:\n'+task['requirement']+'\nSelected alternative constraints:\n'+item['option']+'\nBaseline:\n'+encode(source)+'\nDiff:\n'+item.get('task_patch',item['patch'])+'\nDependency context:\n'+encode({k:v for k,v in item['files'].items() if k not in task['editable']})+'\nActual frozen test reports:\n'+encode({'public':item['public'],'holdout':item['holdout'],'dependencies':item.get('dependency_reports',[])}),owner='candidate:'+item['id'])
            if not isinstance(verdict,dict) or verdict.get('verdict') not in {'PASS','FAIL','UNKNOWN'} or not isinstance(verdict.get('findings'),list) or not all(isinstance(x,str) for x in verdict['findings']):raise ValueError('Invalid cloud review schema')
            item['cloud']=verdict;item['state']='verified' if verdict['verdict']=='PASS' else 'review_required'
            item.pop('review_error',None)
            if verdict['verdict']=='PASS':item.pop('failure_decision',None)
        except Exception as error:
            item['state']='review_required';item['review_error']=str(error)
        self.store.candidate(item['id'],run,item)
        self.emit(run,'candidate_reviewed',{'candidate':item['id'],'state':item['state'],'cloud':item.get('cloud'),'error':item.get('review_error')})
        if item['state']=='review_required':
            verdict=(item.get('cloud') or {}).get('verdict')
            self._apply_failure_decision(run,task,item,{'tests_failed':False,'syntax_failed':False,'review_failed':verdict=='FAIL','review_unknown':verdict=='UNKNOWN','review_error':bool(item.get('review_error'))},{'review_report':bool(item.get('cloud')),'test_reports':bool(item.get('public') or item.get('holdout'))})
        return item
    def _check_candidate_files(self,run,item):
        self.check_main(run);state=self.store.run(run);repo=Path(state['repository']);tree=Path(item['worktree'])
        if git(tree,'rev-parse','HEAD')!=state['base'] or item['base']!=state['base']:raise ValueError('Candidate baseline changed')
        known=set(git(repo,'ls-files','-z').split('\0'))-{''};known|=set(item['files'])
        actual={str(p.relative_to(tree)) for p in tree.rglob('*') if not p.is_dir() and str(p.relative_to(tree))!='.git'}
        if actual!=known:raise ValueError('Candidate tree gained or lost files')
        for name in known:
            path=safe_path(tree,name)
            expected=item['files'][name].encode() if name in item['files'] else safe_path(repo,name).read_bytes()
            if path.read_bytes()!=expected:raise ValueError('Candidate changed after testing: '+name)
        if sha(encode(item['files']))!=item['source_digest']:raise ValueError('Candidate digest mismatch')
    def resume_review(self,run,candidate):
        import fcntl
        with (self.home/'execution.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            state=self.store.run(run);item=self.store.candidate(candidate)
            if not item or item not in self.store.candidates(run):raise ValueError('Unknown candidate for this run')
            self._check_candidate_files(run,item)
            if item['state']=='verified':return {'run':run,'state':'verified','candidate':candidate}
            if item['state'] not in {'tested','reviewing','review_required'} or item.get('cloud'):raise ValueError('Only an unfinished review can resume; a completed verdict requires a revision')
            task=next(t for t in state['tasks'] if t['id']==item['task'])
            decision=decide(task_rules(state,task['id']),state['repository'],task['event'],task.get('facts',{}),task.get('evidence',{}))
            if state.get('stopped') or decision['action'] not in {'APPLY','STAGE','FORK'} or state['decisions'].get(task['id'],{}).get('action') in {'DEFER','ESCALATE','STOP'}:raise ValueError('Task decision is held')
            if time.time()>state['deadline']:raise ValueError('Execution window expired; review budget was not reset')
            folder=self.home/'runs'/run
            from .harness_audit import checked_harness
            harness=checked_harness(folder,task['id'],item.get('harness_digest'))
            audits=[json.loads(row[0]) for row in self.store.db.execute("SELECT body FROM ledger WHERE kind='harness_audit'")]
            if not any(a.get('run')==run and a.get('task')==task['id'] and a.get('digest')==item['harness_digest'] and a.get('audit',{}).get('verdict')=='PASS' for a in audits):raise ValueError('Frozen harness lacks a passing audit')
            tree=Path(item['worktree'])
            item['public']=run_tests(tree,[tree/p for p in task['tests']]);item['holdout']=run_tests(tree,[harness]) if item['public']['passed'] else None
            self._check_candidate_files(run,item)
            from .dependencies import context,test_dependencies
            inherited,checks=context(self,run,task)
            item['dependency_reports']=test_dependencies(tree,checks)
            if not all(r['passed'] for r in item['dependency_reports']) or not item['public']['passed'] or not item['holdout'] or not item['holdout']['passed']:
                item['state']='rejected';self.store.candidate(candidate,run,item)
                self._apply_failure_decision(run,task,item,{'tests_failed':True,'syntax_failed':False,'review_failed':False,'review_unknown':False,'review_error':False},{'test_reports':True})
                self.bundle(run);return {'run':run,'state':'rejected','candidate':candidate}
            source={name:inherited.get(name,(Path(state['repository'])/name).read_text() if (Path(state['repository'])/name).exists() else '') for name in task['editable']}
            self._review(run,task,item,source)
            try:self._check_candidate_files(run,item)
            except Exception:
                item['state']='review_required';self.store.candidate(candidate,run,item);raise
            current=self.store.run(run)
            if item['state']=='verified':current['status'][task['id']]='ready'
            self.store.run(run,current);self.emit(run,'review_resumed',{'candidate':candidate,'state':item['state'],'source_digest':item['source_digest']});self.bundle(run)
            return {'run':run,'state':item['state'],'candidate':candidate}
    def bundle(self,run):
        body=self.store.run(run);candidates=self.store.candidates(run)
        report={**body,'candidates':candidates,'metrics':{'ready_tasks':sum(v=='ready' for v in body['status'].values()),'held_tasks':sum(v in {'defer','deferred','escalate'} for v in body['status'].values()),'rejected_candidates':sum(c['state']=='rejected' for c in candidates),'main_writes':0,'original_worktree_unchanged':git(body['repository'],'rev-parse','HEAD')==body['base'] and not git(body['repository'],'status','--porcelain'),'human_monitoring_seconds':None,'rework_seconds':None,'cloud_price':None,'note':'No claim of attention or monetary savings without a human baseline'}}
        folder=self.home/'runs'/run;folder.mkdir(parents=True,exist_ok=True);(folder/'bundle.json').write_text(encode(report))
        lines=['# Decision Bundle',f'Run: {run}',f'Base: {body["base"]}','', '## Decisions']
        for task in body['tasks']:
            decision=body['decisions'].get(task['id'],{});lines.append(f'- {task["id"]}: {body["status"][task["id"]]} / {decision.get("action","pending")} — {decision.get("reason","")}')
        lines+=['','## Alternatives']
        for c in candidates:lines += [f'### {c["id"]} — {c["state"]}',f'Option: {c["option"]}',f'Worktree: {c["worktree"]}',f'Cloud: {encode(c.get("cloud"))}', '```diff',c.get('patch') or c.get('error',''), '```']
        lines+=['','## Usage',encode(body['usage']),'','Original worktree is never merged automatically. Review time, rework and monetary savings are unmeasured.']
        (folder/'bundle.md').write_text('\n'.join(lines));return report
    def select(self,run,candidate):
        self.check_main(run);item=self.store.candidate(candidate)
        if not item or item not in self.store.candidates(run) or item['state']!='verified':raise ValueError('Only a verified candidate belonging to this run can be selected')
        self._check_candidate_files(run,item)
        from .harness_audit import checked_harness
        checked_harness(self.home/'runs'/run,item['task'],item.get('harness_digest'))
        for check in item.get('dependency_checks',[]):
            from .harness_audit import assert_harness_logic
            source=Path(check['harness']).read_text()
            if sha(source)!=check['digest']:raise ValueError('Dependency harness changed')
            assert_harness_logic(source)
        actual={name:(Path(item['worktree'])/name).read_text() for name in item['files']}
        if sha(encode(actual))!=item['source_digest']:raise ValueError('Candidate changed after verification')
        path=self.home/'runs'/run/(candidate+'.patch');path.write_text(item['patch'])
        self.emit(run,'operator_selected',{'candidate':candidate,'patch':str(path),'source_digest':item['source_digest'],'merged':False});return path
    def close(self):self.store.close()
