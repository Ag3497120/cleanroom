"""Admission rules are enforced on the Mac, never by the public page."""
import contextlib
import datetime as dt
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3
import time
from zoneinfo import ZoneInfo

SPARK = "gpt-5.3-codex-spark"
LANGUAGES = ("ja", "en", "zh-Hans", "ko", "es")
ACTIVE = ("PENDING", "APPROVED", "RUNNING")
def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class Refused(ValueError):
    pass

def parameter_count(details):
    raw = details.get("parameter_size", "")
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([BMK])\s*", raw, re.I)
    if not match:
        return None
    try:
        count = Decimal(match[1]) * {"B":10**9, "M":10**6, "K":1000}[match[2].upper()]
        return int(count) if count > 0 else None
    except (InvalidOperation, OverflowError):
        return None

def validate_pair(models, inspection, implementation, *, owner=False):
    selected = []
    for name in (inspection, implementation):
        if name == SPARK:
            if not owner: raise Refused("SPARK_OWNER_ONLY")
            selected.append({"name":name,"digest":"subscription-owner-only","parameters":0,"provider":"codex"})
        else:
            model = next((m for m in models if m["name"] == name), None)
            if not model: raise Refused("MODEL_NOT_INSTALLED")
            if not model.get("parameters"): raise Refused("PARAMETERS_UNKNOWN")
            selected.append(model)
    if inspection == implementation or selected[0]["digest"] == selected[1]["digest"]:
        raise Refused("DISTINCT_MODELS_REQUIRED")
    total = sum(m["parameters"] for m in selected)
    if total > 40_000_000_000: raise Refused("PAIR_OVER_40B")
    return {"inspection":selected[0],"implementation":selected[1],"total_parameters":total,"reasoning_effort":"low"}

class Store:
    def __init__(self, directory, clock=time.time):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.clock = clock
        self.db = sqlite3.connect(self.directory / "gateway.db", isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, subject TEXT NOT NULL, login TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, subject TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, day TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL, result TEXT, UNIQUE(subject,key));
CREATE TABLE IF NOT EXISTS uses(day TEXT NOT NULL, subject TEXT NOT NULL, bucket TEXT NOT NULL, job TEXT UNIQUE NOT NULL, PRIMARY KEY(day,subject));
CREATE TABLE IF NOT EXISTS policy(day TEXT PRIMARY KEY, spark_limit INTEGER NOT NULL DEFAULT 100, local_only INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS alerts(day TEXT NOT NULL, kind TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(day,kind));
CREATE TABLE IF NOT EXISTS audit(n INTEGER PRIMARY KEY, at REAL NOT NULL, event TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS blocked(subject TEXT PRIMARY KEY);
""")
        # A crash never means success, nor permission to execute an approved job twice.
        self.db.execute("UPDATE jobs SET status='UNKNOWN' WHERE status='RUNNING'")
        self.db.execute("UPDATE jobs SET status='EXPIRED' WHERE status IN ('PENDING','APPROVED')")
        (self.directory / "gateway.db").chmod(0o600)

    def day(self): return dt.datetime.fromtimestamp(self.clock(), ZoneInfo("Asia/Tokyo")).date().isoformat()
    @contextlib.contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try: yield; self.db.execute("COMMIT")
        except BaseException: self.db.execute("ROLLBACK"); raise
    def audit(self,event,body):
        self.db.execute("INSERT INTO audit(at,event,body) VALUES(?,?,?)",(self.clock(),event,json.dumps(body,ensure_ascii=False)))
    def session(self, subject, login):
        token = secrets.token_urlsafe(32)
        self.db.execute("DELETE FROM sessions WHERE expires < ?", (self.clock(),))
        self.db.execute("INSERT INTO sessions VALUES(?,?,?,?)",(digest(token),str(subject),login,self.clock()+86400))
        return token
    def identity(self, token):
        row = self.db.execute("SELECT subject,login FROM sessions WHERE token=? AND expires>?",(digest(token),self.clock())).fetchone()
        if not row or self.db.execute("SELECT 1 FROM blocked WHERE subject=?",(row["subject"],)).fetchone(): raise Refused("LOGIN_REQUIRED")
        return dict(row)
    def policy(self):
        row=self.db.execute("SELECT * FROM policy WHERE day=?",(self.day(),)).fetchone()
        return dict(row) if row else {"day":self.day(),"spark_limit":100,"local_only":0}
    def set_policy(self, mode, limit=None):
        p=self.policy()
        if mode=="local": p["local_only"]=1
        elif mode=="limit" and type(limit) is int and 100 <= limit <= 10000: p["spark_limit"]=limit
        else: raise Refused("INVALID_POLICY")
        with self.transaction():
            self.db.execute("INSERT OR REPLACE INTO policy VALUES(?,?,?)",(p["day"],p["spark_limit"],p["local_only"]))
            self.audit("owner_policy",p)
        return p
    def _admission(self, subject, pair):
        if self.db.execute("SELECT 1 FROM blocked WHERE subject=?",(subject,)).fetchone(): raise Refused("ACCOUNT_BLOCKED")
        if self.db.execute("SELECT 1 FROM uses WHERE day=? AND subject=?",(self.day(),subject)).fetchone(): raise Refused("ONE_REQUEST_PER_DAY")
        bucket="spark" if any(pair[r]["name"]==SPARK for r in ("inspection","implementation")) else "local"
        p=self.policy()
        if bucket=="spark":
            if p["local_only"]: raise Refused("LOCAL_ONLY_TODAY")
            n=self.db.execute("SELECT count(*) FROM uses WHERE day=? AND bucket='spark'",(self.day(),)).fetchone()[0]
            if n>=p["spark_limit"]: raise Refused("SPARK_DAILY_LIMIT")
        return bucket
    def submit(self, identity, body):
        if set(body)!={"request","locale","pair","key"} or body["locale"] not in LANGUAGES: raise Refused("INVALID_REQUEST")
        if type(body["request"]) is not str or not body["request"].strip() or len(body["request"].encode())>16000: raise Refused("INVALID_REQUEST")
        if type(body["key"]) is not str or not re.fullmatch(r"[a-zA-Z0-9-]{16,80}",body["key"]): raise Refused("INVALID_REQUEST")
        subject=identity["subject"]; fp=digest(body)
        with self.transaction():
            old=self.db.execute("SELECT * FROM jobs WHERE subject=? AND key=?",(subject,body["key"])).fetchone()
            if old:
                if old["fingerprint"]!=fp: raise Refused("REQUEST_CHANGED")
                return self.get(old["id"],subject)
            self.db.execute("UPDATE jobs SET status='EXPIRED' WHERE status IN ('PENDING','APPROVED') AND expires<=?",(self.clock(),))
            if self.db.execute("SELECT 1 FROM jobs WHERE subject=? AND status IN ('PENDING','APPROVED','RUNNING')",(subject,)).fetchone(): raise Refused("REQUEST_ALREADY_PENDING")
            if self.db.execute("SELECT count(*) FROM jobs WHERE status IN ('PENDING','APPROVED','RUNNING')").fetchone()[0]>=100: raise Refused("QUEUE_FULL")
            self._admission(subject,body["pair"])
            job="job-"+secrets.token_urlsafe(24)
            self.db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,NULL)",(job,subject,body["key"],fp,json.dumps(body,ensure_ascii=False),"PENDING",self.day(),self.clock(),self.clock()+600))
            self.audit("submitted",{"job":job,"subject":subject,"fingerprint":fp})
            return self.get(job,subject)
    def get(self, job, subject=None):
        row=self.db.execute("SELECT * FROM jobs WHERE id=?"+(" AND subject=?" if subject else ""),(job,subject) if subject else (job,)).fetchone()
        if not row: raise Refused("NOT_FOUND")
        r=dict(row);r["body"]=json.loads(r["body"]);r["result"]=json.loads(r["result"]) if r["result"] else None
        return r
    def approve(self, job, fingerprint, accepted):
        with self.transaction():
            r=self.get(job)
            if r["status"]!="PENDING" or r["fingerprint"]!=fingerprint: raise Refused("APPROVAL_STALE")
            status="APPROVED" if accepted else "REJECTED"
            if r["expires"]<=self.clock() or r["day"]!=self.day(): status="EXPIRED"
            self.db.execute("UPDATE jobs SET status=? WHERE id=?",(status,job))
            self.audit("owner_decision",{"job":job,"fingerprint":fingerprint,"status":status})
    def claim(self, job, current_pair):
        with self.transaction():
            r=self.get(job)
            if r["status"]!="APPROVED": raise Refused("APPROVAL_REQUIRED")
            if r["expires"]<=self.clock() or r["day"]!=self.day(): raise Refused("APPROVAL_EXPIRED")
            if digest(current_pair)!=digest(r["body"]["pair"]): raise Refused("MODEL_CHANGED_REAPPROVE")
            bucket=self._admission(r["subject"],current_pair)
            self.db.execute("INSERT INTO uses VALUES(?,?,?,?)",(self.day(),r["subject"],bucket,job))
            self.db.execute("UPDATE jobs SET status='RUNNING' WHERE id=?",(job,))
            self.audit("started",{"job":job,"bucket":bucket})
    def finish(self, job, status, result=None):
        if status not in ("SUCCEEDED","FAILED","CANCELLED","UNKNOWN"): raise Refused("INVALID_STATUS")
        self.db.execute("UPDATE jobs SET status=?,result=? WHERE id=?",(status,json.dumps(result,ensure_ascii=False),job))
        self.audit("finished",{"job":job,"status":status})
