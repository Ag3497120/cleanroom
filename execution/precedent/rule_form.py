"""Human-facing rule entry. Creates drafts; never changes active policy in place."""
import datetime as dt,math,uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .policy import validate

EVENT_LABELS={'公開する機能の変更':'PUBLIC_API_CHANGE','新しい依存の追加':'NEW_DEPENDENCY','テストと仕様の食い違い':'TEST_SPEC_CONFLICT','要望の解釈が複数ある':'AMBIGUOUS_REQUIREMENT','処理速度の低下':'PERFORMANCE_REGRESSION','権限の拡大':'SECURITY_SCOPE_EXPANSION','人間の編集との衝突':'HUMAN_EDIT_CONFLICT','検証の不合格':'FAILED_VERIFICATION','案を区別する根拠がない':'NO_SEPARATING_SIGNAL','取り消せない操作':'IRREVERSIBLE_ACTION'}
ACTION_LABELS={'1案を実装する':'APPLY','1案を確認用に残す':'STAGE','複数案を作って比較する':'FORK','この仕事を保留する':'DEFER','人間の判断を求める':'ESCALATE','実行を停止する':'STOP'}

def conditions(rows):
    result={}
    for key,kind,value in rows:
        if not key.strip() and not value.strip():continue
        key=key.strip()
        if not key or key in result:raise ValueError('条件の項目名を入力し、重複をなくしてください。')
        try:
            if kind=='文字':parsed=value
            elif kind=='整数':parsed=int(value)
            elif kind=='小数':
                parsed=float(value)
                if not math.isfinite(parsed):raise ValueError()
            elif kind=='真偽':
                if value not in {'はい','いいえ'}:raise ValueError()
                parsed=value=='はい'
            elif kind=='値なし':
                if value.strip():raise ValueError()
                parsed=None
            else:raise ValueError()
        except ValueError:raise ValueError(key+' の値が選択した種類と一致しません。')
        result[key]=parsed
    return result

def draft(name,folder,all_folders,event,action,when,exceptions,evidence,examples,counterexamples,expires):
    if event not in EVENT_LABELS or action not in ACTION_LABELS:raise ValueError('状況と行動を選んでください。')
    if not all_folders and not folder.strip():raise ValueError('対象の作業場所を選んでください。')
    if all_folders:scope='*'
    else:
        path=Path(folder).expanduser().resolve()
        if not path.is_dir():raise ValueError('対象の作業場所が見つかりません。')
        scope=''.join({'*':'[*]','?':'[?]','[':'[[]',']':'[]]'}.get(c,c) for c in str(path))
    expiry=None
    if expires.strip():
        try:expiry=dt.datetime.combine(dt.date.fromisoformat(expires.strip()),dt.time(23,59,59)).astimezone().isoformat()
        except ValueError:raise ValueError('期限は YYYY-MM-DD の日付で入力してください。')
    lines=lambda text:[x.strip() for x in text.splitlines() if x.strip()]
    excluded=conditions(exceptions)
    rule={'id':name.strip() or 'judgment-'+uuid.uuid4().hex[:10],'scope':{'repository':scope,'event':EVENT_LABELS[event]},'when':conditions(when),'action':ACTION_LABELS[action],'evidence_required':lines(evidence),'exceptions':[excluded] if excluded else [],'expires':expiry,'examples':lines(examples),'counterexamples':lines(counterexamples),'status':'DRAFT','version':1}
    validate(rule);return rule

def summary(rule):
    event=next((k for k,v in EVENT_LABELS.items() if v==rule['scope']['event']),rule['scope']['event'])
    action=next((k for k,v in ACTION_LABELS.items() if v==rule['action']),rule['action'])
    return '\n'.join(['判断: '+rule['id'],'対象: '+rule['scope']['repository'],'状況: '+event,'行動: '+action,'一致条件: '+str(rule['when'] or 'なし'),'除外条件: '+str(rule['exceptions'] or 'なし'),'必要な証拠: '+', '.join(rule['evidence_required']),'期限: '+str(rule['expires'] or 'なし'),'当てはまる例: '+' / '.join(rule['examples']),'当てはまらない例: '+' / '.join(rule['counterexamples']),'状態: '+rule['status'],'権限拡大・取り消せない操作は、この判断でも自動実行されません。'])

class RuleForm:
    def __init__(self,parent,on_save):
        self.on_save=on_save;self.window=tk.Toplevel(parent);self.window.title('事前判断を登録');self.window.geometry('760x680');self.window.transient(parent)
        tabs=ttk.Notebook(self.window);tabs.pack(fill='both',expand=True,padx=12,pady=8)
        basic=ttk.Frame(tabs,padding=12);detail=ttk.Frame(tabs,padding=12);tabs.add(basic,text='状況と判断');tabs.add(detail,text='条件と例外')
        self.fields={}
        for label,key in [('判断の名前（空欄なら自動）','name'),('対象の作業場所','folder'),('期限（任意・YYYY-MM-DD）','expires')]:
            ttk.Label(basic,text=label).pack(anchor='w');entry=ttk.Entry(basic);entry.pack(fill='x',pady=4);self.fields[key]=entry
        ttk.Button(basic,text='作業場所を選ぶ',command=self.browse).pack(anchor='w')
        self.all_folders=tk.BooleanVar(value=False);ttk.Checkbutton(basic,text='すべての作業場所を対象にする',variable=self.all_folders).pack(anchor='w',pady=5)
        for label,key,values in [('どの状況で','event',EVENT_LABELS),('どうするか','action',ACTION_LABELS)]:
            ttk.Label(basic,text=label).pack(anchor='w');entry=ttk.Combobox(basic,values=list(values),state='readonly');entry.pack(fill='x',pady=4);self.fields[key]=entry
        self.fields['event'].set('要望の解釈が複数ある');self.fields['action'].set('この仕事を保留する')
        for label,key in [('当てはまる例（1行に1つ）','examples'),('当てはまらない例（1行に1つ）','counterexamples')]:
            ttk.Label(basic,text=label).pack(anchor='w');entry=tk.Text(basic,height=3);entry.pack(fill='x',pady=4);self.fields[key]=entry
        self.rows={}
        for label,key in [('すべて一致したときだけ適用','when'),('すべて一致した場合は除外','exceptions')]:
            box=ttk.LabelFrame(detail,text=label,padding=8);box.pack(fill='x',pady=6);self.rows[key]=[]
            for _ in range(3):
                row=ttk.Frame(box);row.pack(fill='x',pady=3)
                item=ttk.Entry(row,width=23);item.pack(side='left');kind=ttk.Combobox(row,values=['文字','整数','小数','真偽','値なし'],state='readonly',width=8);kind.set('文字');kind.pack(side='left',padx=5);value=ttk.Entry(row);value.pack(side='left',fill='x',expand=True);self.rows[key].append((item,kind,value))
        ttk.Label(detail,text='各行は「項目名・値の種類・一致させる値」です。真偽は「はい」「いいえ」。\n項目名は仕事が報告するものと一致させます。不明な条件は保留になります。').pack(anchor='w')
        ttk.Label(detail,text='必要な証拠の項目名（任意・1行に1つ）').pack(anchor='w',pady=8);self.fields['evidence']=tk.Text(detail,height=3);self.fields['evidence'].pack(fill='x')
        ttk.Label(self.window,text='保存すると下書きになります。内容・例・反例を確認してから有効化できます。').pack(anchor='w',padx=12)
        ttk.Button(self.window,text='下書きとして保存',command=self.save).pack(pady=10)
    def browse(self):
        folder=filedialog.askdirectory(parent=self.window)
        if folder:self.fields['folder'].delete(0,'end');self.fields['folder'].insert(0,folder)
    def save(self):
        try:
            values={key:(entry.get('1.0','end') if isinstance(entry,tk.Text) else entry.get()) for key,entry in self.fields.items()}
            rule=draft(**values,all_folders=self.all_folders.get(),**{key:[tuple(e.get() for e in row) for row in rows] for key,rows in self.rows.items()})
            self.on_save(rule);self.window.destroy()
        except Exception as error:messagebox.showerror('下書きを保存できません',str(error),parent=self.window)
