"""Exercise v0.6 with two artificial generators and real local verification.

All data, decisions and answers are fixtures. No production memory or live AI.
The same script can run against an installed wheel outside the source tree.
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--cross", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(exist_ok=False)
    project = output / "project"
    project.mkdir()
    receipts = output / "receipts"
    receipts.mkdir()
    os.environ["VERANTYX_CROSS"] = str(Path(args.cross).resolve())
    commands, checks = [], []

    def save(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        return path

    def cli(*argv, locale="ja", plain=False):
        command = [sys.executable, "-m", "verantyx", "--project", str(project), "--lang", locale]
        if not plain:
            command += ["--json"]
        result = subprocess.run([*command, *map(str, argv)], capture_output=True, text=True, timeout=60)
        commands.append({"argv": list(map(str, argv)), "locale": locale, "exit_code": result.returncode})
        path = receipts / (str(len(commands)).zfill(3) + (".txt" if plain else ".json"))
        path.write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout if plain else json.loads(result.stdout)

    def check(name, condition, **details):
        checks.append({"name": name, "passed": bool(condition), **details})
        if not condition:
            raise AssertionError(name)

    cli("setup", "--non-interactive", "--name", "Hybrid fixture", "--learning", "digest", "--max-items", "3")
    adapters = []
    for generator in ("A", "B"):
        script = output / ("generator-" + generator + ".py")
        script.write_text('''import json,sys
from pathlib import Path
v=json.load(sys.stdin)
with Path(__file__).with_suffix('.requests.jsonl').open('a') as f: f.write(json.dumps(v,ensure_ascii=False)+'\\n')
if v['format']=='verantyx.proposal-request.v1':
 d=v['proposal_template']; task=v['task']; component=task['context']['component']
 d['summary']='GENERAL ANSWER: '+task['request']
 d['claims']=[{'id':'property','statement':'The selected result meets the fixed property.', 'source_refs':[v['selected_files'][0]['source_ref']]}]
 if component=='http':
  rules=[r for r in v.get('context_assets',{}).get('rules',[]) if r['decision_type']=='retry_policy']
  options=rules[0]['options'] if rules else [{'id':'once','label':'再送しても一度だけ反映する'},{'id':'duplicate','label':'再送で重複反映を許容する'}]
  d['decision_points']=[{'id':'retry-behavior','kind':'VALUE_DECISION','decision_type':'retry_policy','question':'How should retries apply changes?','options':options}]
else:
 d=v['response_template']; component=v['task']['context']['component']
 d['answer']='GENERAL ANSWER: '+v['task']['request']
 ref=v['task']['source_ref']
 if v['max_learning_items']:
  d['learning_candidates']=[{'concept_id':component+'_principle','concept':{'http':'冪等性と再送','conversion':'変換前後の情報の保存','geometry':'形状と数値検査の範囲'}[component], 'why_now':'This task needs a check that can detect the actual failure.', 'minimum_model':'Specify an invariant and an input that breaks it.', 'counterexample':'A file opens but the domain property is false.', 'check':'Design a failing input and explain the expected result.', 'source_refs':[ref]}]
 d['reusable_candidates']=[{'kind':'VERIFICATION_IDEA','title':component+' invariant','situation':'The task produces a structured result.', 'procedure':'Check the fixed expected property and a counterexample.', 'counterexample':'Successful parsing without a correct value.', 'source_refs':[ref]}]
print(json.dumps(d,ensure_ascii=False))
''')
        adapters.append(save(output / ("adapter-" + generator + ".json"), {"argv": [sys.executable, str(script)]}))

    from verantyx.domain.verification import AXES
    from verantyx import __version__
    for domain, pointer, expected, wrong in (("http", "applied_count", 1, 2), ("conversion", "rows", 3, 2), ("geometry", "perimeter", 12, 10)):
        filename = domain + ".json"
        save(project / filename, {pointer: wrong})
        result = cli("ask", domain + "の結果を検討し、再利用できる検査と学ぶ原理を残す", "--task-id", domain,
                     "--adapter", adapters[0], "--key", "ask-" + domain, "--include", filename,
                     "--component", domain, "--workload", "checking", "--risk", "HIGH")
        state = result["state"]
        check(domain + "_answer_and_automatic_learning", state["latest_response"]["mode"] == "GENERATED"
              and len(state["learning_candidates"]) >= 1 and "GENERAL ANSWER" in state["latest_response"]["document"]["answer"])
        check(domain + "_cross_used_by_response", state["latest_response"]["response_structure"]["mode"] == "CROSS_VM")
        if domain == "http":
            decision = cli("decide", domain, "--point", "retry-behavior", "--choice", "once", "--reason", "人工試験: 二重反映を防ぐ")
            precedent = decision["precedent_id"]
            cli("precedent-accept", precedent)
            drafted = cli("rule-draft", precedent)
            rule = drafted["rule_id"]
            for command in ("rule-shadow", "rule-confirm", "rule-activate"):
                cli(command, rule)
        spec = {"claim_id": "property", "target_path": filename, "property": pointer + " equals " + str(expected), "method": "TEST",
                "checks": [{"id": "fixed", "kind": "json.equals", "pointer": "/" + pointer, "expected": expected}],
                "negative_controls": [], "reproduces": None, "oracle": {"description": "Explicit artificial expected value", "source_refs": []},
                "provenance": {axis: "" for axis in AXES}}
        plan = cli("verify-plan", domain, "--spec", save(output / (domain + "-spec.json"), spec), "--key", "plan-" + domain)
        failed = cli("verify-run", domain, "--verification", plan["verification_id"], "--key", "check-" + domain)
        check(domain + "_failure_has_system_and_learning_assets", failed["verification"]["receipt"]["result"]["closure"] == "REFUTED"
              and bool(failed["state"]["deltas"]["human_delta"]))
        response = cli("respond", domain, "--adapter", adapters[1], "--key", "explain-" + domain,
                       "--expected-revision", failed["state"]["revision"])
        check(domain + "_failure_selects_retest", response["state"]["latest_response"]["response_structure"]["result"]["route"] == "RETEST")
        display = cli("replay", domain, plain=True)
        check(domain + "_visible_answer_and_natural_status", "GENERAL ANSWER" in display and "UNKNOWN" not in display and "REFUTED" not in display)
        dictionary = cli("dictionary", "--run", domain)["catalog"]
        check(domain + "_dictionary_has_failure_and_method", bool(dictionary["failure_cases"]) and bool(dictionary["verification_methods"]))
        method = next(item for item in dictionary["verification_methods"] if item["owner_run"] == domain)
        fixed = domain + "-fixed.json"
        save(project / fixed, {pointer: expected})
        next_task = domain + "-reuse"
        reused = cli("ask", "Reuse the recorded " + domain + " check", "--task-id", next_task,
                     "--adapter", adapters[1], "--key", "ask-" + next_task, "--include", fixed,
                     "--component", domain, "--workload", "checking", "--risk", "HIGH", locale="en")
        if domain == "http":
            check("second_generator_preserves_canonical_rule_contract_across_locale",
                  reused["state"]["assessment"]["judgments"][0]["status"] == "PRECEDENT_MATCHED")
        saved_spec = output / (domain + "-reused-spec.json")
        cli("asset-template", method["id"], "--claim", "property", "--target", fixed, "--output", saved_spec)
        planned = cli("verify-plan", next_task, "--spec", saved_spec, "--key", "reuse-plan-" + domain)
        checked = cli("verify-run", next_task, "--verification", planned["verification_id"], "--key", "reuse-check-" + domain)
        check(domain + "_saved_contract_runs_on_new_target", checked["verification"]["receipt"]["result"]["closure"] == "BOUNDED")
    final = cli("dictionary")
    check("unverified_model_ideas_are_separate", bool(final["catalog"]["reuse_candidates"])
          and all(item["verification"] == "UNVERIFIED" for item in final["catalog"]["reuse_candidates"]))
    report = {"version": __version__, "passed": all(item["passed"] for item in checks), "checks": checks,
              "cli_invocations": len(commands), "domains": ["http", "conversion", "geometry"], "artificial_generators": 2,
              "live_model_calls": 0, "production_memory_writes": 0, "human_understanding_assessed": False}
    save(output / "commands.json", commands)
    save(output / "report.json", report)
    print(json.dumps({"passed": report["passed"], "cli_invocations": len(commands), "checks": len(checks), "report": str(output / "report.json")}))


if __name__ == "__main__":
    main()
