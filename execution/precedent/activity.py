"""Read-only run evidence summary, never inferred human attention or savings."""
import json
from collections import Counter
from datetime import datetime,timezone

# These APIs can also be called by automation. They do not identify a human actor.
CONTROL_LABELS={
    'adapter_replaced':'接続先の明示変更',
    'routing_configured':'自動切替の設定',
    'task_judgment_reconsidered':'保留仕事への判断の再適用',
    'dependencies_selected':'先行案の選択',
    'execution_window_renewed':'実行時間の再設定',
    'review_resumed':'レビュー再開の結果',
    'operator_selected':'検証済み案の保存',
    'handoff_prepared':'引継ぎ資料の作成',
    'handoff_dispatch_started':'接続先への実装依頼開始',
}

def report(store,run):
    state=store.run(run)
    if not state:raise ValueError('Unknown run')
    integrity=store.verify_ledger()
    if not integrity['valid']:return {'schema':3,'run':run,'summary_available':False,'ledger_consistency':integrity,'scope':'Ledger inconsistency prevents a reliable activity summary. Original records are preserved.'}
    counts=Counter();operations=[];automatic=[];failures=[]
    for seq,at,kind,raw,digest in store.db.execute('SELECT seq,at,kind,body,hash FROM ledger ORDER BY seq'):
        body=json.loads(raw)
        if body.get('run')!=run:continue
        counts[kind]+=1
        item={'seq':seq,'at':at,'kind':kind,'ledger_hash':digest}
        # Keep evidence references and outcomes, not full prompts or generated code.
        for key in ('task','candidate','role','adapter','old','new','state','handoff'):
            if key in body:item[key]=body[key]
        if kind in CONTROL_LABELS:operations.append({**item,'label':CONTROL_LABELS[kind]})
        elif kind=='handoff_response_received' and body.get('origin')=='operator_supplied_unverified':operations.append({**item,'label':'回答ファイルの持込み（作成元未検証）'})
        elif kind=='adapter_auto_replaced':automatic.append(item)
        if kind=='transport_observation' and body.get('outcome')!='valid_response':failures.append({**item,'outcome':body.get('outcome'),'provider':body.get('provider')})
    held=[]
    for task,status in state.get('status',{}).items():
        if status in {'defer','deferred','escalate','stop','failed','running'}:
            decision=state.get('decisions',{}).get(task,{})
            held.append({'task':task,'state':status,'reason':decision.get('execution_error') or decision.get('reason') or '保存状態を確認してください。'})
    candidates=store.candidates(run)
    from .attention import summary
    attention=summary(store,run)
    return {'schema':3,'summary_available':True,'ledger_consistency':integrity,'run':run,'explicit_attention':attention,'recorded_control_operations':len(operations),'control_operations':operations,'automatic_switches':automatic,'transport_failures':failures,'event_counts':dict(counts),'current_task_attention':held,'current_candidate_attention':[{'candidate':c['id'],'task':c['task'],'state':c['state'],'reason':c.get('review_error') or c.get('error') or ''} for c in candidates if c['state'] not in {'verified','selected'}],'usage':state.get('usage',{}),'human_interventions':None,'human_monitoring_seconds':None,'rework_seconds':None,'savings_percent':None,'scope':'Counts are persisted API operation records, not human actions, clicks or attention time. Automation can call these APIs. Failed calls without a ledger record, unrecorded resumes and model-wide settings are not counted. Event hashes reference records; ledger_consistency separately checks only internal chain consistency.'}

def describe(body):
    if body.get('summary_available') is False:
        integrity=body['ledger_consistency']
        return f"実行: {body['run']}\n保存履歴に不整合があります。\n問題の記録番号: {integrity['issue_seq']}\n一致を確認できた先頭の記録数: {integrity['checked']}\n履歴の集計は利用できません。記録を保持したまま、新しい推論と実行再開を停止しています。\nこの診断をファイルへ保存できます。"
    lines=[f"実行: {body['run']}",f"記録された明示操作: {body['recorded_control_operations']}件",f"自動切替: {len(body['automatic_switches'])}件 / 接続・応答形式の失敗: {len(body['transport_failures'])}件",'明示操作はAPIに残った記録数です。自動化からも呼べるため、人間の介入回数とは異なります。','未記録の失敗・再開、モデル全体の設定変更は集計対象外です。','監視時間・やり直し時間・削減率は未測定です。','','現在の確認対象']
    for item in body['current_task_attention']:lines.append(f"仕事 {item['task']} / {item['state']}: {item['reason']}")
    for item in body['current_candidate_attention']:lines.append(f"候補 {item['candidate']} / {item['state']}: {item['reason']}")
    if not body['current_task_attention'] and not body['current_candidate_attention']:lines.append('保存状態に確認対象はありません。仕事全体の完了を保証する表示ではありません。')
    lines+=['','明示操作の履歴（記録順、UTC）']
    for item in body['control_operations']:
        date=datetime.fromtimestamp(item['at'],timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        target=' / '.join(str(item[key]) for key in ('task','candidate','role','adapter') if key in item)
        lines.append(f"#{item['seq']} {date} {item['label']} {target}")
    if not body['control_operations']:lines.append('該当する記録はありません。人間の介入がゼロだったことを意味しません。')
    integrity=body.get('ledger_consistency',{})
    lines+=['','保存履歴の内部照合: '+('一致' if integrity.get('valid') else '不一致・確認が必要'),'これは履歴内の整合性だけの照合です。履歴全体の差替え、末尾の削除、別テーブルの変更を証明・検出するものではありません。']
    attention=body.get('explicit_attention',{})
    seconds=attention.get('completed_elapsed_seconds')
    lines+=['','明示的に記録した区間',('完了区間の合計: '+format(seconds,'.1f')+'秒') if seconds is not None else '完了した計測区間はありません。',f"未終了: {attention.get('unfinished_count',0)}件 / 時間不明で閉じた区間: {attention.get('abandoned_count',0)}件",'離席や記録漏れは検出しません。この合計は人間の監視時間や削減率ではありません。']
    for row in attention.get('intervals',[]):lines.append(f"#{row['start_seq']} {row['category']} / {row['state']} / "+(format(row['seconds'],'.1f')+'秒' if row['seconds'] is not None else '時間不明'))
    return '\n'.join(lines)
