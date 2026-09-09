"""Prepare a task manifest from explicit human input; never starts execution."""
import copy,re,uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from .execution import git,safe_path
from .rule_form import EVENT_LABELS,conditions

def assemble(current,folder,name,requirement,editable,tests,options,depends,event,model,facts=(),evidence=''):
    if not folder.strip():raise ValueError('対象の作業場所を選んでください。')
    repo=Path(folder).expanduser().resolve()
    if git(repo,'rev-parse','--show-toplevel')!=str(repo):raise ValueError('Git作業場所の一番上のフォルダーを選んでください。')
    if not requirement.strip():raise ValueError('実現したいことを入力してください。')
    key=name.strip() or 'task-'+uuid.uuid4().hex[:8]
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',key):raise ValueError('仕事IDは半角英数字・ハイフン・下線の80文字以内です。')
    if event not in EVENT_LABELS:raise ValueError('判断する状況を選んでください。')
    lines=lambda value:list(dict.fromkeys(x.strip() for x in value.splitlines() if x.strip()))
    edits=lines(editable);fixed=lines(tests)
    if not edits or not fixed:raise ValueError('変更対象と固定テストをそれぞれ指定してください。')
    for path in edits+fixed:safe_path(repo,path)
    if any(not safe_path(repo,path).is_file() for path in fixed):raise ValueError('固定テストには存在するファイルを指定してください。')
    result=copy.deepcopy(current) if current else {'repository':str(repo),'tasks':[],'local_model':model.strip() or 'qwen2.5:3b'}
    if not isinstance(result,dict) or not isinstance(result.get('tasks'),list):raise ValueError('既存の実行内容を確認してください。')
    if Path(result['repository']).resolve()!=repo:raise ValueError('追加先と同じ作業場所を選んでください。新しい実行は詳細欄を空にしてから作成できます。')
    if current and model.strip() and model.strip()!=result.get('local_model','qwen2.5:3b'):raise ValueError('仕事追加時に既存のモデル設定は変更できません。')
    ids={t['id'] for t in result['tasks']};parents=lines(depends)
    if key in ids:raise ValueError('同じ仕事IDがあります。')
    if not set(parents)<=ids:raise ValueError('依存先には、既に追加した仕事IDを指定してください。')
    all_tests=set(fixed)|{p for t in result['tasks'] for p in t['tests']}
    if set(edits)&all_tests or any(set(t['editable'])&all_tests for t in result['tasks']):raise ValueError('固定テストを変更対象にはできません。')
    variants=lines(options) or ['Implement the requirement']
    maximum=result.get('limits',{}).get('max_candidates',2)
    if type(maximum) is not int or maximum<1:raise ValueError('候補数の上限を確認してください。')
    if len(variants)>maximum:raise ValueError('現在の比較案の上限は'+str(maximum)+'案です。案を絞るか、実行内容の上限を明示的に変更してください。')
    task={'id':key,'requirement':requirement.strip(),'event':EVENT_LABELS[event],'editable':edits,'tests':fixed,'options':variants,'depends_on':parents,'facts':conditions(facts),'evidence':{key:True for key in lines(evidence)}}
    result['tasks'].append(task);return result

class TaskForm:
    def __init__(self,parent,current,on_save):
        self.current=current;self.on_save=on_save;self.window=tk.Toplevel(parent);self.window.title('実行する仕事を追加');self.window.geometry('780x680');self.window.transient(parent)
        tabs=ttk.Notebook(self.window);tabs.pack(fill='both',expand=True,padx=12,pady=8);basic=ttk.Frame(tabs,padding=12);scope=ttk.Frame(tabs,padding=12);facts=ttk.Frame(tabs,padding=12)
        for page,label in [(basic,'仕様と比較案'),(scope,'作業範囲と依存先'),(facts,'判断に使う情報')]:tabs.add(page,text=label)
        self.fields={}
        for page,label,key,initial in [(basic,'仕事ID（空欄なら自動）','name',''),(scope,'Git作業場所','folder',current.get('repository','')),(scope,'ローカルモデル名','model',current.get('local_model','qwen2.5:3b'))]:
            ttk.Label(page,text=label).pack(anchor='w');entry=ttk.Entry(page);entry.insert(0,initial);entry.pack(fill='x',pady=5);self.fields[key]=entry
        ttk.Button(scope,text='作業場所を選ぶ',command=self.browse).pack(anchor='w')
        for page,label,key,height in [(basic,'実現したいこと・満たすべき仕様','requirement',7),(basic,'比較したい案（任意・既定最大2案・1行に1案）','options',4),(scope,'変更してよいファイル（作業場所からの相対パス・1行に1つ）','editable',3),(scope,'固定するテスト（相対パス・1行に1つ）','tests',3),(scope,'先に必要な仕事ID（任意・1行に1つ）','depends',2)]:
            ttk.Label(page,text=label).pack(anchor='w',pady=4);entry=tk.Text(page,height=height);entry.pack(fill='x');self.fields[key]=entry
        ttk.Label(basic,text='どの状況として事前判断を適用するか').pack(anchor='w',pady=8);event=ttk.Combobox(basic,values=list(EVENT_LABELS),state='readonly');event.set('要望の解釈が複数ある');event.pack(fill='x');self.fields['event']=event
        ttk.Label(facts,text='判断に使う事実（項目名・種類・値）。未入力の情報は推測しません。').pack(anchor='w',pady=8);self.rows=[]
        for _ in range(3):
            row=ttk.Frame(facts);row.pack(fill='x',pady=5);key=ttk.Entry(row,width=24);key.pack(side='left');kind=ttk.Combobox(row,values=['文字','整数','小数','真偽','値なし'],state='readonly',width=8);kind.set('文字');kind.pack(side='left',padx=5);value=ttk.Entry(row);value.pack(side='left',fill='x',expand=True);self.rows.append((key,kind,value))
        ttk.Label(facts,text='自分が確認した証拠の項目名（任意・1行に1つ）').pack(anchor='w',pady=8);self.fields['evidence']=tk.Text(facts,height=4);self.fields['evidence'].pack(fill='x')
        ttk.Label(self.window,text='実行内容に追加するだけです。開始には「事前判断に従って実行」を使います。').pack(anchor='w',padx=12)
        ttk.Button(self.window,text='実行内容に追加',command=self.save).pack(pady=10)
    def browse(self):
        folder=filedialog.askdirectory(parent=self.window)
        if folder:self.fields['folder'].delete(0,'end');self.fields['folder'].insert(0,folder)
    def save(self):
        try:
            values={key:entry.get('1.0','end') if isinstance(entry,tk.Text) else entry.get() for key,entry in self.fields.items()}
            result=assemble(self.current,**values,facts=[tuple(e.get() for e in row) for row in self.rows]);self.on_save(result);self.window.destroy()
        except Exception as error:messagebox.showerror('仕事を追加できません',str(error),parent=self.window)
