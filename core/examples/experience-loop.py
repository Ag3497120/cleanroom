"""Run the ownership loop in a disposable project with two artificial generators.

This is an executable wiring example, not a live-model quality evaluation.
It preserves command receipts and does not use the production Vera memory.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "src/verantyx").is_dir():
    sys.path.insert(0, str(ROOT / "src"))
    os.environ["PYTHONPATH"] = str(ROOT / "src")

GENERATOR = r'''
from pathlib import Path
import base64,json,sys
v=json.load(sys.stdin)
with Path(LOG_PATH).open('a') as log: log.write(json.dumps({'generator':sys.argv[1],'format':v['format']})+'\n')
if v['format']=='verantyx.proposal-request.v1':
 d=v['proposal_template'];d.update(summary='An artificial candidate for the fixed example.',actions=[],unknowns=[],decision_points=[])
 d['claims']=[dict(id='property',statement='The fixed example property holds.',source_refs=[v['task']['source_ref']])]
elif v['format']=='verantyx.handoff-plan-request.v1':
 d=v['response_template'];s=v['shared_context']['sources'][0]
 d['interpretations']=[dict(id='requirement',source_id=s['id'],quote=s['text'],meaning='Preserve the frozen calculator tests.',disposition='NOW',strength='MUST',alternatives=[])]
 d['relations']=[]
 d['cases']=[dict(id='fixed-tests',situation='May the frozen test expectation be changed?',choices=[dict(id='no',text='Keep the expectation'),dict(id='yes',text='Change the expectation')],expected='no',interpretation_ids=['requirement'])]
elif v['format']=='verantyx.editor-request.v1':
 d=v['response_template'];p=v['interpretation_proposal']
 d['acknowledgements']=[dict(id=n['id'],disposition=n['disposition'],strength=n['strength'],interpretation=n['meaning'],alternatives=n['alternatives']) for n in p['interpretations']]
 d['relations']=p['relations'];d['case_choices']=[dict(id='fixed-tests',choice='no',reason='The fixed test stays unchanged.')]
 d['files']={'calc.py':'def answer():\n    return '+('999' if sys.argv[1]=='editor-A' else '2')+'\n'}
 d['tests']=['test_calc.py'];d['notes']='Artificial code candidate; its behavior requires actual tests.'
elif v['format']=='verantyx.asset-workflow-request.v1':
 c=v['context'];target=c['selected_files'][0]
 d={'format':'verantyx.asset-workflow-plan.v1','context_sha256':v['context_sha256'],'steps':[
 {'id':'count','mode':'COMPILE','claim_id':'property','target_path':target['path'],'asset_id':None,
  'property':'The fixture count equals one.','method':'NEGATIVE_CONTROL','checks':[{'id':'count','kind':'json.equals','pointer':'/count','expected':1}],
  'negative_controls':[{'id':'wrong-count','input_base64':base64.b64encode(b'{"count":0}').decode()}],
  'expectation_basis':'Explicit synthetic fixture contract: count=1.','source_refs':[c['request_ref']]}],'unresolved':[]}
else:
 d=v['response_template'];d['answer']='人工生成器の候補です。実際の検査結果・判断・学習項目は下の記録を参照できます。'
 d['reusable_candidates']=[];d['learning_candidates']=[]
 if v['max_learning_items']:
  d['learning_candidates']=[dict(concept_id='fixed_contract',concept='期待値を固定して失敗を検出する',why_now='今回の候補を固定した条件で確認したため。',minimum_model='結果に合わせて期待値を変えない。',counterexample='失敗した後にテストを書き換えて成功にする。',check='失敗を検出するために何を固定したか説明する。',source_refs=[v['task']['source_ref']])]
print(json.dumps(d))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cross", required=True)
    parser.add_argument("--precedent", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(exist_ok=False)
    project = output / "project"
    project.mkdir()
    (output / "receipts").mkdir()
    os.environ["VERANTYX_CROSS"] = str(Path(args.cross).resolve())
    commands, checks = [], []

    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return path

    def cli(*values, expected=0):
        argv = [sys.executable, "-m", "verantyx", "--project", str(project), "--lang", "ja", "--json", *map(str, values)]
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=90)
        receipt = json.loads(completed.stdout)
        number = len(commands) + 1
        save(output / "receipts" / (str(number).zfill(3) + ".json"), receipt)
        commands.append({"argv": argv, "exit_code": completed.returncode})
        assert completed.returncode == expected, (values, completed.returncode, receipt.get("error"), completed.stderr[-1000:])
        return receipt

    def check(name, value):
        checks.append({"name": name, "passed": bool(value)})
        assert value, name

    cli("setup", "--non-interactive", "--learning", "digest", "--max-items", "3")
    adapters = {}
    for name in ("A", "B", "editor-A", "editor-B"):
        script = output / (name + ".py")
        script.write_text(GENERATOR.replace("LOG_PATH", repr(str(output / "calls.jsonl"))))
        adapters[name] = save(output / (name + ".json"), {"argv": [sys.executable, str(script), name]})
    project.joinpath("calc.py").write_text("def answer():\n    return 1\n")
    project.joinpath("test_calc.py").write_text("import unittest\nfrom calc import answer\nclass Fixed(unittest.TestCase):\n    def test_answer(self): self.assertEqual(answer(),2)\n")
    for operation in (["init", "-q"], ["add", "calc.py", "test_calc.py"],
                      ["-c", "user.name=Artificial fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Fixed source"]):
        subprocess.run(["git", "-C", str(project), *operation], check=True, capture_output=True)
    common = ["--include", "calc.py", "--include", "test_calc.py", "--component", "calculator", "--workload", "local", "--risk", "LOW"]
    first = cli("ask", "固定したテストを維持して計算器を直す", "--task-id", "first", "--key", "first",
                "--adapter", adapters["A"], "--editor-adapter", adapters["editor-A"], "--execute-candidate", "--precedent", args.precedent, *common)
    check("unresolved_decision_blocks_execution", first["work_loop"]["status"] == "BLOCKED" and not first["state"]["effects"])
    point = first["state"]["assessment"]["question"]["point_id"]
    decision = cli("decide", "first", "--point", point, "--choice", "isolate", "--reason", "人工試験の方針。本人の判断を表すものではない。", "--key", "decision")
    precedent = decision["precedent_id"]
    cli("precedent-accept", precedent, "--key", "accept")
    rule = cli("rule-draft", precedent, "--key", "draft")["rule_id"]
    for operation in ("rule-shadow", "rule-confirm", "rule-activate"):
        cli(operation, rule, "--key", operation)
    state = cli("replay", "first")["state"]
    failed = cli("work", "first", "--key", "execute-A", "--expected-revision", state["revision"], "--execute", "--precedent", args.precedent, expected=4)
    check("bad_code_is_refuted_by_real_frozen_tests", failed["work_loop"]["status"] == "REFUTED")
    check("failure_is_recovered", bool(failed["state"]["deltas"]["system_delta"]["failure_assets"]))
    fixed = cli("ask", "同じ範囲で固定テストを維持して計算器を直す", "--task-id", "second", "--key", "second",
                "--adapter", adapters["B"], "--editor-adapter", adapters["editor-B"], "--execute-candidate", "--precedent", args.precedent, *common)
    check("B_reuses_decision_and_tests_candidate", fixed["execution_ok"] and not fixed["state"]["human_decisions"]
          and fixed["state"]["deltas"]["system_delta"]["reused_rules"])
    check("canonical_source_is_preserved", project.joinpath("calc.py").read_text().endswith("return 1\n"))
    project.joinpath("bad-counter.json").write_text('{"count":2}')
    project.joinpath("good-counter.json").write_text('{"count":1}')
    bad = cli("ask", "人工条件count=1で検査する", "--task-id", "counter-A", "--key", "counter-A", "--adapter", adapters["A"],
              "--include", "bad-counter.json", "--auto-check")
    check("finite_contract_captures_failure", bad["asset_workflow"]["status"] == "REFUTED")
    method = bad["state"]["deltas"]["system_delta"]["verification_assets"][0]["id"]
    cli("ask", "保存したcountの検査を別の結果へ適用する", "--task-id", "counter-B", "--key", "counter-B", "--adapter", adapters["B"], "--include", "good-counter.json")
    for name in ("A", "editor-A"):
        adapters[name].unlink()
        output.joinpath(name + ".py").unlink()
    count = len(output.joinpath("calls.jsonl").read_text().splitlines())
    reused = cli("asset-loop", "counter-B", "--asset", method, "--claim", "property", "--target", "good-counter.json", "--key", "reuse")
    check("model_removed_and_no_call_needed_for_reuse", reused["ok"] and reused["model_calls"] == 0
          and len(output.joinpath("calls.jsonl").read_text().splitlines()) == count)
    source_spec = bad["asset_workflow"]["plan"]["steps"][0]["spec"]
    new_spec = reused["workflow"]["plan"]["steps"][0]["spec"]
    check("expectations_and_negative_control_stay_fixed", all(source_spec[k] == new_spec[k] for k in ("checks", "negative_controls", "property", "method")))
    check("negative_control_actually_rejected", reused["workflow"]["results"][0]["closure"] == "BOUNDED")
    repeated = cli("asset-loop", "counter-B", "--asset", method, "--claim", "property", "--target", "good-counter.json", "--key", "reuse")
    check("repeated_command_uses_same_receipt", repeated["projection_hash"] == reused["projection_hash"])
    candidate = next(iter(bad["state"]["learning_candidates"]))
    cli("learn-target", "counter-A", "--candidate", candidate, "--target", "REVIEW", "--reason", "人工試験の任意学習選択", "--key", "learn-choice")
    measured = cli("sovereignty")
    check("report_counts_real_assets_without_claiming_mastery", measured["metrics"]["reused_decisions"] >= 1
          and measured["metrics"]["model_free_reuses"] == 1 and measured["metrics"]["retained_failures"] >= 2
          and measured["human_selected_targets"]["REVIEW"] == 1 and measured["unmeasured"]["human_mastery"] is None)
    from verantyx import __version__
    report = {"version": __version__, "passed": all(row["passed"] for row in checks), "checks": checks,
              "cli_invocations": len(commands), "live_model_calls": 0, "artificial_generators": True,
              "production_memory_writes": 0, "metrics": measured["metrics"]}
    save(output / "commands.json", commands)
    save(output / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
