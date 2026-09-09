import argparse,json
from pathlib import Path
from .engine import Engine,compile_precedent
from .store import Store

def main():
    p=argparse.ArgumentParser(description='Precedent — scoped judgment and speculative coding')
    p.add_argument('--home',type=Path,default=Path('state'))
    s=p.add_subparsers(dest='command',required=True)
    s.add_parser('gui')
    c=s.add_parser('bind-dependencies');c.add_argument('run');c.add_argument('task');c.add_argument('selections',type=Path)
    s.add_parser('adapters')
    s.add_parser('verify-evidence')
    c=s.add_parser('activity');c.add_argument('run')
    c=s.add_parser('suggest-profile');c.add_argument('run')
    c=s.add_parser('trial-profile');c.add_argument('run');c.add_argument('options',type=Path)
    c=s.add_parser('activate-profile');c.add_argument('trial')
    c=s.add_parser('reset-profile');c.add_argument('model')
    c=s.add_parser('reconsider-task');c.add_argument('run');c.add_argument('task')
    c=s.add_parser('check-adapter');c.add_argument('run');c.add_argument('adapter')
    c=s.add_parser('configure-routing');c.add_argument('run');c.add_argument('rules',type=Path)
    c=s.add_parser('recommend-adapter');c.add_argument('run');c.add_argument('role')
    c=s.add_parser('renew-window');c.add_argument('run');c.add_argument('--seconds',type=int,required=True);c.add_argument('--expected-deadline',type=float,required=True)
    c=s.add_parser('record-desktop-state');c.add_argument('path',type=Path)
    c=s.add_parser('dispatch');c.add_argument('handoff');c.add_argument('task');c.add_argument('--option')
    c=s.add_parser('import-response');c.add_argument('path',type=Path)
    c=s.add_parser('bind');c.add_argument('run');c.add_argument('role');c.add_argument('adapter')
    c=s.add_parser('handoff');c.add_argument('run');c.add_argument('adapter')
    c=s.add_parser('compile');c.add_argument('text');c.add_argument('--model',default='qwen2.5:3b')
    c=s.add_parser('import-rule');c.add_argument('path',type=Path)
    c=s.add_parser('transition');c.add_argument('id');c.add_argument('status',choices=['SHADOW','CONFIRMED','ACTIVE','RETIRED'])
    s.add_parser('rules')
    c=s.add_parser('run');c.add_argument('manifest',type=Path)
    for name in ('resume','bundle'):
        c=s.add_parser(name);c.add_argument('run')
    c=s.add_parser('resume-review');c.add_argument('run');c.add_argument('candidate')
    c=s.add_parser('select');c.add_argument('run');c.add_argument('candidate')
    a=p.parse_args()
    if a.command=='record-desktop-state':
        from .desktop_state import record
        store=Store(a.home)
        try:print(json.dumps(record(store,**json.loads(a.path.read_text())),ensure_ascii=False,indent=2))
        finally:store.close()
        return
    if a.command in {'adapters','bind','handoff'}:
        from .adapters import discover,bind,capsule
        store=Store(a.home)
        try:
            result=discover(a.home) if a.command=='adapters' else bind(store,a.run,a.role,a.adapter) if a.command=='bind' else capsule(store,a.run,a.adapter)
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:store.close()
        return
    if a.command=='gui':
        from .app import App
        App(a.home).main();return
    if a.command in {'compile','import-rule','transition','rules'}:
        store=Store(a.home)
        try:
            if a.command=='compile':rule,usage=compile_precedent(a.text,a.model);result=store.save_rule(rule);store.event('calibration',{'utterance':a.text,'usage':usage})
            elif a.command=='import-rule':result=store.save_rule(json.loads(a.path.read_text()))
            elif a.command=='transition':result=store.transition(a.id,a.status)
            else:result=store.rules()
            print(json.dumps(result,ensure_ascii=False,indent=2))
        finally:store.close()
        return
    engine=Engine(a.home)
    try:
        if a.command=='run':
            key=engine.create(json.loads(a.manifest.read_text()));print(json.dumps({'run':key}),flush=True);result=engine.execute(key)
        elif a.command=='verify-evidence':result=engine.store.verify_ledger()
        elif a.command=='activity':
            from .activity import report
            result=report(engine.store,a.run)
        elif a.command=='dispatch':
            from .adapters import dispatch
            result=dispatch(engine,a.handoff,a.task,a.option)
        elif a.command=='import-response':
            from .adapters import import_response
            result=import_response(engine,a.path)
        elif a.command=='suggest-profile':
            from .profiles import suggest
            result=suggest(engine.store,a.run)
        elif a.command=='trial-profile':
            from .profiles import evaluate
            result=evaluate(engine,a.run,json.loads(a.options.read_text()))
        elif a.command=='activate-profile':
            from .profiles import activate
            result=activate(engine,a.trial)
        elif a.command=='reset-profile':
            from .profiles import reset
            result=reset(engine,a.model)
        elif a.command=='reconsider-task':
            from .reconsider import reconsider
            result=reconsider(engine,a.run,a.task)
        elif a.command=='check-adapter':
            from .capabilities import check
            state=engine.store.run(a.run)
            if not state:raise ValueError('Unknown run')
            result=check(a.adapter,state['local_model'])
        elif a.command=='configure-routing':
            from .routing import configure
            result=configure(engine,a.run,json.loads(a.rules.read_text()))
        elif a.command=='recommend-adapter':
            from .transport_health import recommendations
            result=recommendations(engine.store,a.run,a.role)
        elif a.command=='bind-dependencies':
            from .dependencies import bind
            result=bind(engine,a.run,a.task,json.loads(a.selections.read_text()))
        elif a.command=='renew-window':result=engine.renew_window(a.run,a.seconds,a.expected_deadline)
        elif a.command=='resume-review':result=engine.resume_review(a.run,a.candidate)
        elif a.command=='resume':result=engine.execute(a.run)
        elif a.command=='bundle':result=engine.bundle(a.run)
        else:result={'patch':str(engine.select(a.run,a.candidate))}
        print(json.dumps(result,ensure_ascii=False,indent=2))
        if a.command=='verify-evidence' and not result['valid']:raise SystemExit(1)
    finally:engine.close()

if __name__=='__main__':main()
