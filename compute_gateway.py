"""Authenticated public job API; the private PTY server is never exposed."""
import argparse
import asyncio
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import ssl
import time
from urllib.parse import urlsplit

import certifi
from aiohttp import web, ClientSession, ClientTimeout, TCPConnector, ClientError
from compute_routing import loopback_endpoint, small_pair
from gateway_policy import Store, Refused, validate_pair, parameter_count, SPARK, LANGUAGES, digest

ROOT=Path(__file__).resolve().parent
CANON=Path(os.environ.get('VERANTYX_HOME',str(ROOT/'core'))).expanduser().resolve()
def script_args(script, *args):
    return ["/usr/bin/osascript","-e",script,"--",*map(str,args)]

APPROVAL_SCRIPT='''on run argv
set answer to display dialog (item 1 of argv) with title "Verantyx — 計算資源の利用確認" buttons {"拒否", "この依頼を許可"} default button "拒否" giving up after 300
if gave up of answer then return "deny"
if button returned of answer is "この依頼を許可" then return "allow"
return "deny"
end run'''
NOTICE_SCRIPT='''on run argv
set answer to display dialog (item 1 of argv) with title "Verantyx — 利用上限" buttons {"閉じる", "管理画面を開く"} default button "閉じる" giving up after 120
if button returned of answer is "管理画面を開く" then open location (item 2 of argv)
end run'''
MAIL_SCRIPT='''on run argv
tell application "Mail"
set outgoing to make new outgoing message with properties {subject:"Verantyx — 本日のSpark利用上限", content:(item 2 of argv), visible:false}
tell outgoing
make new to recipient at end of to recipients with properties {address:(item 1 of argv)}
send
end tell
end tell
end run'''

async def bounded_process(argv, *, cwd=None, stdin=None, timeout=600, limit=4*1024*1024):
    process=await asyncio.create_subprocess_exec(*map(str,argv),cwd=cwd,stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,start_new_session=True)
    async def read(stream):
        parts=[];size=0
        while chunk:=await stream.read(16384):
            size+=len(chunk)
            if size>limit: raise Refused("PROCESS_OUTPUT_LIMIT")
            parts.append(chunk)
        return b"".join(parts)
    async def write():
        if stdin is not None:
            process.stdin.write(stdin);await process.stdin.drain();process.stdin.close()
    tasks=[asyncio.create_task(read(process.stdout)),asyncio.create_task(read(process.stderr)),asyncio.create_task(write())]
    try:
        async with asyncio.timeout(timeout):
            out,err,_=await asyncio.gather(*tasks)
            code=await process.wait()
        return code,out,err
    finally:
        for task in tasks: task.cancel()
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError): os.killpg(process.pid,signal.SIGTERM)
            try: await asyncio.wait_for(process.wait(),2)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError): os.killpg(process.pid,signal.SIGKILL)
                await process.wait()

class Gateway:
    def __init__(self, config, *, clock=time.time):
        self.cfg=config
        self.clock=clock
        self.site=config["site_url"].rstrip("/")+"/"
        site=urlsplit(self.site); api=urlsplit(config["gateway_url"])
        if (site.scheme!="https" or api.scheme!="https" or not site.hostname or not api.hostname
                or site.username or api.username or site.password or api.password or site.query or site.fragment
                or api.path not in ("", "/") or api.query or api.fragment):
            raise ValueError("GitHub Pages and gateway need explicit HTTPS URLs")
        self.site_origin=f"{site.scheme}://{site.netloc}"
        self.api_host=api.netloc
        self.directory=Path(config["state_dir"]).expanduser().resolve()
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.lock=(self.directory/"process.lock").open("a")
        fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        self.store=Store(self.directory,clock)
        self.http=None
        self.flows={}
        self.tasks=set()
        self.active={}
        self.owner_token=secrets.token_urlsafe(32)
        self.owner_port=config.get("owner_port",8767)
        self.owner_url=f"http://127.0.0.1:{self.owner_port}/owner"
        self.model_cache=None
        self.model_time=0
        self.rate={}
        self.admission_lock=asyncio.Lock()
        self.reservations={}
        self.endpoints={'primary':loopback_endpoint(config.get('primary_ollama','http://127.0.0.1:11434'))}
        if config.get('secondary_ollama'):
            self.endpoints['backup-24GB']=loopback_endpoint(config['secondary_ollama'])

    def throttle(self, key, count=30, seconds=60):
        now=self.clock()
        recent=[t for t in self.rate.get(key,[]) if t>now-seconds]
        if len(recent)>=count: raise Refused("RATE_LIMIT")
        self.rate[key]=recent+[now]
        if len(self.rate)>5000: self.rate={k:v for k,v in self.rate.items() if v[-1]>now-seconds}
    def spawn(self,coro):
        task=asyncio.create_task(coro);self.tasks.add(task);task.add_done_callback(self.tasks.discard);return task

    @web.middleware
    async def public_guard(self, request, handler):
        if request.host!=self.api_host: raise web.HTTPForbidden()
        origin=request.headers.get("Origin")
        if origin!=self.site_origin: raise web.HTTPForbidden()
        headers={"Access-Control-Allow-Origin":self.site_origin,"Vary":"Origin","Cache-Control":"no-store",
                 "X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer"}
        if request.method=="OPTIONS":
            return web.Response(headers={**headers,"Access-Control-Allow-Methods":"GET,POST,DELETE,OPTIONS","Access-Control-Allow-Headers":"Authorization,Content-Type"})
        try:
            # Only the authenticated identity grants usage. IPs are not proof of a person.
            self.throttle(("transport",request.remote),300)
            result=await handler(request)
        except Refused as error:
            result=web.json_response({"error":str(error)},status=401 if str(error)=="LOGIN_REQUIRED" else 409)
        except (ValueError,KeyError,TypeError):
            result=web.json_response({"error":"INVALID_REQUEST"},status=400)
        for k,v in headers.items(): result.headers[k]=v
        return result

    def identity(self, request):
        auth=request.headers.get("Authorization","")
        if not auth.startswith("Bearer "): raise Refused("LOGIN_REQUIRED")
        return self.store.identity(auth[7:])

    async def inventory(self, force=False, node="primary"):
        if node=="primary" and not force and self.model_cache is not None and self.clock()-self.model_time<30: return self.model_cache
        try:
            async with self.http.get(self.endpoints[node]+"/api/tags",timeout=ClientTimeout(total=3)) as response:
                if response.status!=200: raise Refused("OLLAMA_UNAVAILABLE")
                data=await response.json()
            models=[]
            for item in data["models"]:
                name=item["name"]
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}",name): continue
                models.append({"name":name,"digest":item["digest"],"parameters":parameter_count(item.get("details",{})),"provider":"ollama"})
            if node=="primary": self.model_cache=models;self.model_time=self.clock()
            return models
        except (OSError,asyncio.TimeoutError,ClientError):
            raise Refused("OLLAMA_UNAVAILABLE") from None

    async def catalog(self,request):
        identity=self.identity(request) if request.headers.get("Authorization") else None
        models=await self.inventory()
        return web.json_response({"models":models,"spark":{"name":SPARK,"available":bool(identity and identity["subject"]==str(self.cfg["owner_github_id"])),"owner_only":True,"effort":"low"},
            "languages":LANGUAGES,"max_pair_parameters":40_000_000_000,"identity":identity,"policy":self.store.policy(),"requests_per_account_per_day":1})

    async def login_start(self,request):
        self.throttle(("login",request.remote),5,300)
        client=self.cfg.get("github_client_id")
        if not client: raise Refused("GITHUB_LOGIN_NOT_CONFIGURED")
        async with self.http.post("https://github.com/login/device/code",data={"client_id":client,"scope":""},headers={"Accept":"application/json"}) as res:
            data=await res.json()
        if "device_code" not in data or data.get("verification_uri")!="https://github.com/login/device": raise Refused("GITHUB_LOGIN_FAILED")
        key=secrets.token_urlsafe(32);now=self.clock()
        self.flows={k:v for k,v in self.flows.items() if v["expires"]>now}
        if len(self.flows)>=100: raise Refused("LOGIN_BUSY")
        interval=max(5,int(data.get("interval",5)))
        self.flows[digest(key)]={"device":data["device_code"],"expires":now+min(900,data["expires_in"]),"next":now+interval,"interval":interval}
        return web.json_response({"flow":key,"code":data["user_code"],"url":data["verification_uri"],"interval":interval})

    async def login_poll(self,request):
        body=await request.json(); flow=self.flows.get(digest(body["flow"]))
        if not flow or flow["expires"]<self.clock(): raise Refused("LOGIN_EXPIRED")
        if flow.get("busy") or flow["next"]>self.clock(): return web.json_response({"pending":True,"interval":flow["interval"]})
        flow["busy"]=True;flow["next"]=self.clock()+flow["interval"]
        try:
            async with self.http.post("https://github.com/login/oauth/access_token",data={"client_id":self.cfg["github_client_id"],"device_code":flow["device"],
                "grant_type":"urn:ietf:params:oauth:grant-type:device_code"},headers={"Accept":"application/json"}) as res: data=await res.json()
            if data.get("error") in ("authorization_pending","slow_down"):
                if data["error"]=="slow_down": flow["interval"]+=5;flow["next"]=self.clock()+flow["interval"]
                return web.json_response({"pending":True,"interval":flow["interval"]})
            token=data.get("access_token")
            if not token: self.flows.pop(digest(body["flow"]),None);raise Refused("GITHUB_LOGIN_FAILED")
            async with self.http.get("https://api.github.com/user",headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","User-Agent":"Verantyx"}) as res:
                user=await res.json()
                if res.status!=200 or type(user.get("id")) is not int: raise Refused("GITHUB_LOGIN_FAILED")
            # Discard the GitHub token; the browser only gets a revocable local session.
            session=self.store.session(str(user["id"]),user["login"])
            self.flows.pop(digest(body["flow"]),None)
            return web.json_response({"token":session,"login":user["login"]})
        finally: flow["busy"]=False

    async def submit(self,request):
        who=self.identity(request);self.throttle(("submit",who["subject"]),10)
        body=await request.json()
        if set(body)!={"request","locale","inspection","implementation","key"}: raise Refused("INVALID_REQUEST")
        async with self.admission_lock:
            old=self.store.db.execute("SELECT id FROM jobs WHERE subject=? AND key=?",(who['subject'],body['key'])).fetchone()
            if old:
                job=self.store.get(old['id'],who['subject'])
                saved=job['body']; requested=saved['pair'].get('requested_models',{})
                if any(body[k]!=saved[k] for k in ('request','locale')) or any(body[r]!=requested.get(r,saved['pair'][r]['name']) for r in ('inspection','implementation')):
                    raise Refused('REQUEST_CHANGED')
                return web.json_response(self.public_job(job),status=202)
            pair=validate_pair(await self.inventory(),body['inspection'],body['implementation'],owner=who['subject']==str(self.cfg['owner_github_id']))
            node='primary'
            if node in self.reservations:
                node='backup-24GB'
                if node not in self.endpoints or node in self.reservations: raise Refused('COMPUTE_BUSY')
                try:
                    available=await self.inventory(force=True,node=node)
                    if self.cfg.get('secondary_models'):
                        available=[m for m in available if m['name'] in self.cfg['secondary_models']]
                    pair=small_pair(available)
                except (Refused,ValueError,KeyError,TypeError): raise Refused('COMPUTE_BUSY') from None
            pair['compute_node']=node
            pair['requested_models']={r:body[r] for r in ('inspection','implementation')}
            try: job=self.store.submit(who,{'request':body['request'],'locale':body['locale'],'pair':pair,'key':body['key']})
            except Refused as error:
                if str(error)=='SPARK_DAILY_LIMIT': self.spawn(self.quota_notice())
                raise
            self.reservations[node]=job['id']
            task=self.spawn(self.run_job(job['id']))
            self.active[job['id']]=task
            def release(_):
                if self.reservations.get(node)==job['id']: self.reservations.pop(node,None)
                self.active.pop(job['id'],None)
            task.add_done_callback(release)
            return web.json_response(self.public_job(job),status=202)

    def public_job(self,job):
        return {**{k:job[k] for k in ("id","status","result","expires")},'compute':{
            'node':job['body']['pair'].get('compute_node','primary'),
            **{r:job['body']['pair'][r]['name'] for r in ('inspection','implementation')}}}
    async def job_status(self,request):
        who=self.identity(request);return web.json_response(self.public_job(self.store.get(request.match_info["job"],who["subject"])))
    async def cancel(self,request):
        who=self.identity(request);job=self.store.get(request.match_info["job"],who["subject"])
        if job["status"] in ("PENDING","APPROVED","RUNNING"):
            self.store.finish(job["id"],"CANCELLED")
            task=self.active.get(job["id"])
            if task: task.cancel()
        return web.json_response(self.public_job(self.store.get(job["id"],who["subject"])))

    async def approve_dialog(self,job):
        body=job["body"];pair=body["pair"]
        message=f"実行先: {pair.get('compute_node','primary')}\n利用者: GitHub ID {job['subject']}\n検査補助: {pair['inspection']['name']}\n実装案: {pair['implementation']['name']}\nローカル合計: {pair['total_parameters']/1e9:g}B / {10 if pair.get('compute_node')=='backup-24GB' else 40}B\n\n{body['request'][:2000]}\n\nこの一件に計算資源を使用しますか？"
        code,out,_=await bounded_process(script_args(APPROVAL_SCRIPT,message),timeout=310,limit=32768)
        return code==0 and out.decode().strip()=="allow"

    async def run_job(self,jobid):
        job=self.store.get(jobid)
        if job["status"]!="PENDING": return
        if job["expires"]<=self.clock() or job["day"]!=self.store.day():
            self.store.approve(jobid,job["fingerprint"],False)
            self.active.pop(jobid,None)
            return
        try:
            approved=await self.approve_dialog(job)
            self.store.approve(jobid,job["fingerprint"],approved)
            if not approved or self.store.get(jobid)["status"]!="APPROVED": return
            old=job["body"]["pair"]
            current=validate_pair(await self.inventory(force=True,node=old.get("compute_node","primary")),old["inspection"]["name"],old["implementation"]["name"],owner=job["subject"]==str(self.cfg["owner_github_id"]))
            if old.get('compute_node')=='backup-24GB' and current['total_parameters']>10_000_000_000: raise Refused('PAIR_OVER_10B')
            for key in ('compute_node','requested_models'):
                if key in old: current[key]=old[key]
            self.store.claim(jobid,current)
            result=await self.execute(job)
            self.store.finish(jobid,"SUCCEEDED",result)
        except asyncio.CancelledError:
            if self.store.get(jobid)["status"] not in ("CANCELLED","UNKNOWN"): self.store.finish(jobid,"UNKNOWN",{"error":"INTERRUPTED"})
            raise
        except Refused as error:
            self.store.finish(jobid,"FAILED",{"error":str(error)})
            if str(error)=="SPARK_DAILY_LIMIT": self.spawn(self.quota_notice())
        except Exception:
            self.store.finish(jobid,"FAILED",{"error":"EXECUTION_FAILED"})
        finally:
            self.active.pop(jobid,None)
            node=job['body']['pair'].get('compute_node','primary')
            if self.reservations.get(node)==jobid: self.reservations.pop(node,None)

    def adapter_profile(self, model, node="primary"):
        if model["provider"]=="codex":
            return {"argv":[self.cfg.get("python","/usr/local/bin/python3"),str(ROOT/"spark_adapter.py")]}
        return {"format":"verantyx.model-api.v1","provider":"ollama","model":model["name"],"endpoint":self.endpoints[node]+"/api/chat","key_env":None,
                "allow_loopback_http":True,"timeout":180,"max_output_tokens":32768,"max_response_bytes":262144,"thinking":False,"context_window":32768}

    async def execute(self,job):
        # This workspace belongs to this authenticated user, not the owner's checkout.
        project=self.directory/"projects"/hashlib.sha256(job["subject"].encode()).hexdigest()
        project.mkdir(parents=True,exist_ok=True,mode=0o700)
        cli=CANON/"bin/verantyx"
        base=[self.cfg.get("python","/usr/local/bin/python3"),cli,"--project",project,"--lang",job["body"]["locale"],"--json"]
        if not (project/".verantyx/config.json").exists():
            code,_,_=await bounded_process(base+["setup","--non-interactive","--name","Web workspace","--purpose","AI assistance","--learning","manual","--max-items","1"],timeout=30)
            if code: raise Refused("WORKSPACE_SETUP_FAILED")
        adapters=[]
        for role in ("inspection","implementation"):
            model=job["body"]["pair"][role]
            target=project/(job["id"]+"-"+role+".json")
            value=self.adapter_profile(model,job["body"]["pair"].get("compute_node","primary"))
            target.write_text(json.dumps(value));target.chmod(0o600);adapters.append(target)
        code,out,_=await bounded_process(base+["ask","--adapter",adapters[0],"--editor-adapter",adapters[1],"--proposal-only","--key",job["id"],"--timeout","180","--max-repairs","0","--",job["body"]["request"]],timeout=900)
        if code: raise Refused("VERANTYX_REQUEST_FAILED")
        value=json.loads(out);state=value.get("state",{})
        response=state.get("latest_response",{})
        if not response.get("document"): raise Refused("RESPONSE_INCOMPLETE")
        return {"answer":response["document"].get("answer",""),"response_mode":response.get("mode"),"run_id":value.get("run_id"),
                "candidate_status":state.get("editor_attempt",{}).get("validation",{}).get("status"),"adopted":False,
                "proposed_files":state.get("editor_attempt",{}).get("document",{}).get("files",{}),"execution_performed":False,
                "learning":list(state.get("learning_candidates",{}).values()),"reuse":response["document"].get("reusable_candidates",[])}

    async def quota_notice(self):
        day=self.store.day()
        inserted=self.store.db.execute("INSERT OR IGNORE INTO alerts(day,kind) VALUES(?,'spark_limit')",(day,)).rowcount
        if not inserted: return
        message="本日のSpark利用者が設定上限に達しました。管理画面でローカルモデルへ切り替えるか、サービス側の人数枠を変更できます。OpenAIの契約上限は変更しません。"
        self.store.audit("quota_notice",{"day":day})
        email=self.cfg.get("notify_email")
        if email:
            try:
                code,_,_=await bounded_process(script_args(MAIL_SCRIPT,email,message+"\n\nこのMacで開く: "+self.owner_url),timeout=30,limit=32768)
                self.store.audit("email_delivery",{"day":day,"sent":code==0})
            except Exception: self.store.audit("email_delivery",{"day":day,"sent":False})
        shown=False
        try:
            code,_,_=await bounded_process(script_args(NOTICE_SCRIPT,message,self.owner_url),timeout=130,limit=32768)
            shown=code==0
            self.store.audit("desktop_notice",{"day":day,"shown":shown})
        except Exception: self.store.audit("desktop_notice",{"day":day,"shown":False})
        self.store.db.execute("UPDATE alerts SET delivered=? WHERE day=? AND kind='spark_limit'",(int(shown),day))

    @web.middleware
    async def owner_guard(self,request,handler):
        allowed=f"127.0.0.1:{self.owner_port}"
        if request.host!=allowed or request.headers.get("Origin","http://"+allowed)!="http://"+allowed: raise web.HTTPForbidden()
        if request.method=="POST" and not secrets.compare_digest(request.headers.get("X-Owner-Token",""),self.owner_token): raise web.HTTPForbidden()
        try: response=await handler(request)
        except Refused as error: response=web.json_response({"error":str(error)},status=409)
        response.headers.update({"Cache-Control":"no-store","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer",
            "Content-Security-Policy":"default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"})
        return response

    async def owner_page(self,request):
        text="""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Verantyx — Mac管理</title>
<style>body{background:#101012;color:#eee;font:16px Menlo,monospace;padding:24px}button,input{font:inherit;background:#202025;color:#eee;border:1px solid #666;padding:10px;margin:8px}pre{white-space:pre-wrap}</style>
<h1>Verantyx — このMacの計算資源</h1><pre id="state">状態を確認しています…</pre><p>この変更は本日分のみです。OpenAIの契約上限やSparkの本人専用制限は変更しません。</p>
<button id="local">本日はローカルモデルを使う</button><label>本日の人数枠 <input id="limit" type="number" min="100" max="10000" value="100"></label><button id="change">人数枠を変更</button>
<p>一人で複数アカウントを使っていると確認した場合は、GitHub IDを利用停止にできます。</p><input id="subject" placeholder="GitHubの数値ID"><button id="block">このIDを停止</button><script src="/owner.js"></script></html>"""
        return web.Response(text=text,content_type="text/html")
    async def owner_js(self,request):
        js="""let token='';async function refresh(){const r=await fetch('/owner/state');const d=await r.json();token=d.token;document.querySelector('#state').textContent=JSON.stringify(d.policy,null,2);}
async function change(body){const r=await fetch('/owner/action',{method:'POST',headers:{'Content-Type':'application/json','X-Owner-Token':token},body:JSON.stringify(body)});if(!r.ok)alert('変更できませんでした');await refresh();}
document.querySelector('#local').onclick=()=>change({mode:'local'});document.querySelector('#change').onclick=()=>change({mode:'limit',limit:Number(document.querySelector('#limit').value)});document.querySelector('#block').onclick=()=>change({mode:'block',subject:document.querySelector('#subject').value});refresh();"""
        return web.Response(text=js,content_type="application/javascript")
    async def owner_state(self,request): return web.json_response({"token":self.owner_token,"policy":self.store.policy()})
    async def owner_action(self,request):
        body=await request.json()
        if body.get("mode")=="block":
            if not re.fullmatch(r"[0-9]{1,20}",str(body.get("subject",""))): raise Refused("INVALID_ID")
            self.store.db.execute("INSERT OR IGNORE INTO blocked VALUES(?)",(body["subject"],))
            self.store.audit("owner_block",{"subject":body["subject"]})
        else: self.store.set_policy(body.get("mode"),body.get("limit"))
        return web.json_response({"ok":True})
    def public_app(self):
        app=web.Application(middlewares=[self.public_guard],client_max_size=24576)
        app.router.add_get("/v1/models",self.catalog)
        app.router.add_post("/v1/login/start",self.login_start)
        app.router.add_post("/v1/login/poll",self.login_poll)
        app.router.add_post("/v1/jobs",self.submit)
        app.router.add_get("/v1/jobs/{job}",self.job_status)
        app.router.add_delete("/v1/jobs/{job}",self.cancel)
        async def not_found(request):
            raise web.HTTPNotFound()
        app.router.add_route("*","/{tail:.*}",not_found)
        return app
    def owner_app(self):
        app=web.Application(middlewares=[self.owner_guard],client_max_size=4096)
        app.router.add_get("/owner",self.owner_page);app.router.add_get("/owner.js",self.owner_js)
        app.router.add_get("/owner/state",self.owner_state);app.router.add_post("/owner/action",self.owner_action)
        return app

async def serve(config):
    gateway=Gateway(config)
    tls=ssl.create_default_context(cafile=certifi.where())
    async with ClientSession(timeout=ClientTimeout(total=15),connector=TCPConnector(ssl=tls)) as client:
        gateway.http=client
        runners=[]
        try:
            for app,port in ((gateway.public_app(),config.get("port",8766)),(gateway.owner_app(),gateway.owner_port)):
                runner=web.AppRunner(app,access_log=None);await runner.setup();runners.append(runner)
                await web.TCPSite(runner,"127.0.0.1",port).start()
            # Jobs reserve a physical compute slot atomically before they start.
            print("Verantyx: 公開用接続の準備完了。Mac側の実行承認を待ちます。",flush=True)
            print("管理画面: "+gateway.owner_url,flush=True)
            stop=asyncio.Event()
            for sig in (signal.SIGINT,signal.SIGTERM): asyncio.get_running_loop().add_signal_handler(sig,stop.set)
            await stop.wait()
        finally:
            for task in gateway.tasks: task.cancel()
            if gateway.tasks: await asyncio.gather(*gateway.tasks,return_exceptions=True)
            for runner in runners: await runner.cleanup()
            gateway.store.db.close();gateway.lock.close()

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--config",required=True)
    args=parser.parse_args();asyncio.run(serve(json.loads(Path(args.config).read_text())))
