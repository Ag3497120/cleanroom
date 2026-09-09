import hashlib,json,sqlite3,time,uuid
from pathlib import Path
from .policy import validate

def encode(x):return json.dumps(x,ensure_ascii=False,sort_keys=True)
def sha(x):return hashlib.sha256(x if isinstance(x,bytes) else x.encode()).hexdigest()

class Store:
    def __init__(self,home):
        self.home=Path(home).resolve();self.home.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.home/'precedent.sqlite')
        self.db.executescript('''PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS rules(id TEXT,version INTEGER,body TEXT,PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS ledger(seq INTEGER PRIMARY KEY,at REAL,kind TEXT,body TEXT,previous TEXT,hash TEXT);
        CREATE TRIGGER IF NOT EXISTS immutable_ledger_update BEFORE UPDATE ON ledger BEGIN SELECT RAISE(ABORT,'append only'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_ledger_delete BEFORE DELETE ON ledger BEGIN SELECT RAISE(ABORT,'append only'); END;
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS desktop_surfaces(id TEXT PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS handoffs(id TEXT PRIMARY KEY,body TEXT,response_digest TEXT,result TEXT);
        CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,run TEXT,body TEXT);
        ''');self.db.commit()
    def verify_ledger(self):
        previous='genesis';checked=0
        for seq,at,kind,raw,parent,digest in self.db.execute('SELECT seq,at,kind,body,previous,hash FROM ledger ORDER BY seq'):
            try:
                body=json.loads(raw)
                if parent!=previous or digest!=sha(encode([at,kind,body,parent])):raise ValueError('hash mismatch')
            except (ValueError,TypeError) as error:
                return {'valid':False,'checked':checked,'head_hash':previous,'issue_seq':seq,'issue':str(error)}
            checked+=1;previous=digest
        return {'valid':True,'checked':checked,'head_hash':previous,'scope':'Internal hash-chain consistency only; not authentication, table-state verification, or detection of whole-chain replacement/tail deletion without an external anchor.'}
    def assert_ledger(self):
        report=self.verify_ledger()
        if not report['valid']:raise RuntimeError('Saved evidence is inconsistent at ledger record '+str(report['issue_seq']))
        return report
    def event(self,kind,body):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            report=self.assert_ledger();previous=report['head_hash']
            at=float(time.time());self.db.execute('INSERT INTO ledger(at,kind,body,previous,hash) VALUES(?,?,?,?,?)',(at,kind,encode(body),previous,sha(encode([at,kind,body,previous]))));self.db.commit()
        except Exception:self.db.rollback();raise
    def rules(self):
        rows=self.db.execute('SELECT body FROM rules r WHERE version=(SELECT MAX(version) FROM rules WHERE id=r.id)').fetchall()
        return [json.loads(r[0]) for r in rows]
    def save_rule(self,rule,status='DRAFT'):
        rule=dict(rule);rule['status']=status
        rule['version']=self.db.execute('SELECT COALESCE(MAX(version),0)+1 FROM rules WHERE id=?',(rule['id'],)).fetchone()[0]
        validate(rule);self.db.execute('INSERT INTO rules VALUES(?,?,?)',(rule['id'],rule['version'],encode(rule)));self.db.commit()
        self.event('rule_version',rule);return rule
    def transition(self,key,status):
        rule=next(r for r in self.rules() if r['id']==key)
        allowed={'DRAFT':{'SHADOW','CONFIRMED','RETIRED'},'SHADOW':{'CONFIRMED','RETIRED'},'CONFIRMED':{'ACTIVE','RETIRED'},'ACTIVE':{'RETIRED'},'RETIRED':set()}
        if status not in allowed[rule['status']]:raise ValueError('Invalid lifecycle transition')
        if status=='CONFIRMED' and (not rule['examples'] or not rule['counterexamples']):raise ValueError('Confirm at least one example and counterexample first')
        return self.save_rule(rule,status)
    def run(self,key,body=None):
        if body is not None:self.db.execute('INSERT OR REPLACE INTO runs VALUES(?,?)',(key,encode(body)));self.db.commit()
        row=self.db.execute('SELECT body FROM runs WHERE id=?',(key,)).fetchone();return json.loads(row[0]) if row else None
    def candidate(self,key,run=None,body=None):
        if body is not None:self.db.execute('INSERT OR REPLACE INTO candidates VALUES(?,?,?)',(key,run,encode(body)));self.db.commit()
        row=self.db.execute('SELECT body FROM candidates WHERE id=?',(key,)).fetchone();return json.loads(row[0]) if row else None
    def candidates(self,run):return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM candidates WHERE run=?',(run,))]
    def close(self):self.db.close()
