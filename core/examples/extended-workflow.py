#!/usr/bin/env python3
"""Exercise v0.4 through the real CLI in a new synthetic local project.

This uses scripted proposals, decisions and quiz answers. It measures command
behavior, not model quality, operator identity or anybody's understanding.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import base64
import importlib.util
import json
import sys

helper = importlib.util.spec_from_file_location("verantyx_demo_helper", Path(__file__).with_name("end-to-end.py"))
demo_module = importlib.util.module_from_spec(helper)
helper.loader.exec_module(demo_module)
Demo, write_json = demo_module.Demo, demo_module.write_json
LANGUAGES = demo_module.LANGUAGES


class ExtendedDemo(Demo):
    def document(self, name, value):
        path = self.output / (name + ".json")
        write_json(path, value)
        return path

    def decision_task(self, task, component="writer", workload="parallel"):
        value = {"schema_version": 1, "task_id": task, "context_revision": 0, "response_locale": "ja",
                 "summary": "Artificial value decision", "claims": [], "actions": [], "unknowns": [],
                 "decision_points": [{"id": "separate", "kind": "VALUE_DECISION", "decision_type": "parallel_writers",
                                      "question": "作業場所を分離しますか？", "options": [
                                          {"id": "isolate", "label": "個別のworktree"}, {"id": "shared", "label": "共有の作業場所"}]}]}
        return self.cli("run-" + task, "run", "Synthetic work request", "--task-id", task,
                        "--component", component, "--workload", workload, "--risk", "HIGH",
                        "--proposal", self.document(task, value))

    def decide(self, task):
        return self.cli("decide-" + task, "decide", task, "--point", "separate", "--choice", "isolate",
                        "--reason", "Synthetic fixture decision", "--key", "decide-" + task)

    def governance(self):
        self.decision_task("policy-origin")
        case = self.decide("policy-origin")["precedent_id"]
        self.cli("case-accept", "precedent-accept", case)
        rule = self.cli("rule-draft", "rule-draft", case)["rule_id"]
        policy = self.cli("policy-template", "rule-policy-template", rule)
        policy["scope"]["component"] = ["compiler", "writer"]
        policy["scope"]["workload"] = ["batch", "parallel"]
        policy["exceptions"] = [{"id": "exception", "scope": {key: values[0] for key, values in policy["scope"].items()},
                                 "reason": "Synthetic fixture exception"}]
        proposed = self.cli("policy-propose", "rule-policy-propose", rule, "--policy", self.document("policy", policy),
                            "--reason", "Synthetic finite scope", "--key", "policy-propose")
        sha = proposed["policy_sha256"]
        self.cli("policy-accept", "rule-policy-accept", rule, "--expected-policy-sha256", sha,
                 "--reason", "Synthetic explicit review", "--key", "policy-accept")
        self.cli("policy-shadow", "rule-shadow", rule)
        for task, component in (("pilot-one", "writer"), ("pilot-two", "compiler")):
            self.decision_task(task, component)
            self.decide(task)
        self.cli("policy-confirm", "rule-policy-confirm", rule, "--expected-policy-sha256", sha,
                 "--reason", "Two fixture tasks inspected", "--key", "policy-confirm")
        for mode in ("WARN", "BLOCK"):
            self.cli("policy-" + mode, "rule-enforce", rule, "--expected-policy-sha256", sha,
                     "--enforcement", mode, "--reason", "Synthetic enforcement selection", "--key", "mode-" + mode)
            if mode == "WARN":
                self.decision_task("policy-warning")
                for locale in LANGUAGES:
                    shown = self.cli("warning-display-" + locale, "replay", "policy-warning", locale=locale, as_json=False)
                    from verantyx.i18n import text
                    self.check("warn_visible_" + locale, text(locale, "presentation.enforcement.WARN") in shown)
        matched = self.decision_task("policy-second", "compiler")
        self.check("finite_scope_reuses_rule", matched["state"]["assessment"]["judgments"][0]["status"] == "PRECEDENT_MATCHED")
        exempt = self.decision_task("policy-exempt", "compiler", "batch")
        self.check("exception_requires_own_decision", exempt["state"]["assessment"]["question"] is not None)
        outside = self.decision_task("policy-outside", "unrelated")
        self.check("outside_scope_not_reused", outside["state"]["assessment"]["question"] is not None)
        report = self.cli("shadow-report", "rule-shadow-report", rule)
        self.check("actual_shadow_observations", report["distinct_tasks"] >= 2)
        self.rule = rule

    def verification(self):
        (self.project / "report.json").write_text('{"answer":42}')
        first = self.cli("verify-task", "run", "Synthetic bounded property", "--task-id", "verify",
                         "--observe", "report.json")
        document = self.cli("claim-template", "proposal-template", "verify")
        document.update(actions=[], claims=[{"id": "answer", "statement": "The answer is 42.",
                         "source_refs": [first["state"]["latest_observations"]["report.json"]]}])
        self.cli("claim-proposal", "resume", "verify", "--proposal", self.document("claim-proposal", document))
        spec = self.cli("verification-template", "verify-template", "verify", "--claim", "answer", "--target", "report.json")
        spec.update(property="JSON /answer equals integer 42", checks=[{"id": "answer", "kind": "json.equals", "pointer": "/answer", "expected": 42}],
                    oracle={"description": "Synthetic expected value fixed before execution", "source_refs": []})
        first_id = None
        for method in ("TEST", "REPRODUCTION", "NEGATIVE_CONTROL"):
            current = json.loads(json.dumps(spec))
            current["method"] = method
            if method == "REPRODUCTION":
                current["reproduces"] = first_id
            elif method == "NEGATIVE_CONTROL":
                current["negative_controls"] = [{"id": "wrong", "input_base64": base64.b64encode(b'{"answer":41}').decode()}]
            plan = self.cli("verify-plan-" + method, "verify-plan", "verify", "--spec", self.document("spec-" + method, current), "--key", "plan-" + method)
            identifier = plan["verification_id"]
            first_id = first_id or identifier
            result = self.cli("verify-run-" + method, "verify-run", "verify", "--verification", identifier, "--key", "verify-" + method)
            self.check("bounded_" + method, result["verification"]["receipt"]["result"]["closure"] == "BOUNDED")
            self.check("no_prose_entailment_" + method, result["state"]["assessment"]["claims"][0]["prose_entailment"] == "NOT_ASSESSED")
            claim = result["state"]["assessment"]["claims"][0]
            self.check("prose_remains_unknown_" + method, claim["epistemic_status"] == "UNKNOWN"
                       and claim["property_evidence"]["closure"] == "BOUNDED")
        self.cli("verification-list", "verifications", "verify")

    def learning(self):
        from verantyx.learning_materials import builtin_exercise
        for locale in LANGUAGES:
            task = "learn-" + locale
            first = self.cli("learn-task-" + locale, "run", "Synthetic voluntary practice", "--task-id", task, locale=locale)
            candidate = self.cli("learn-raise-" + locale, "learn-raise", task, "--candidate", "practice",
                                 "--concept", "Worktree isolation", "--concept-id", "parallel_writers", "--why-now", "Synthetic review",
                                 "--minimum-model", "Separate worktrees", "--counterexample", "Two writers share files",
                                 "--check", "Choose isolated worktrees", "--source-ref", first["state"]["request_ref"],
                                 "--key", "raise-" + locale, locale=locale)
            spec = builtin_exercise("parallel_writers", locale)
            self.cli("exercise-register-" + locale, "learn-exercise-register", task, "--candidate", "practice", "--key", "register-" + locale, locale=locale)
            material = self.cli("exercise-material-" + locale, "learn-material", task, "--candidate", "practice", locale=locale, as_json=False)
            self.check("localized_material_" + locale, spec["lesson"]["title"] in material)
            # These are explicitly scripted fixture answers, not a user assessment.
            answers = {q["id"]: q["rubric"]["expected"] for q in spec["questions"]}
            answer = self.cli("exercise-answer-" + locale, "learn-exercise-answer", task, "--candidate", "practice", "--exercise", spec["id"],
                              "--answers", self.document("answers-" + locale, answers), "--origin", "UNKNOWN", "--identity", "Synthetic fixture",
                              "--key", "answer-" + locale, locale=locale)
            item = next(item for item in answer["candidates"] if item["id"] == "practice")
            assessment = item["exercises"][0]["assessments"][-1]["result"]
            self.check("bounded_learning_" + locale, assessment["status"] == "PASSED" and assessment["mastery_claim"] == "NOT_ASSESSED")
            due = datetime.now(timezone.utc) + timedelta(seconds=30)
            self.cli("review-schedule-" + locale, "learn-review-schedule", task, "--candidate", "practice", "--exercise", spec["id"],
                     "--due", due.isoformat(), "--reason", "Synthetic schedule", "--key", "schedule-" + locale, locale=locale)
            view = self.cli("review-due-" + locale, "learn-due", task, "--at", (due + timedelta(seconds=1)).isoformat(), locale=locale)
            self.check("review_due_" + locale, len(view["items"]) == 1)
            self.cli("review-cancel-" + locale, "learn-review-cancel", task, "--candidate", "practice", "--exercise", spec["id"],
                     "--reason", "Synthetic cancellation", "--key", "cancel-" + locale, locale=locale)
            self.cli("locale-events-" + locale, "events", task, locale=locale, as_json=False)
            material_json = self.cli("material-json-" + locale, "learn-material", task, "--candidate", "practice", locale=locale)
            self.check("public_material_no_rubric_" + locale, '"rubric"' not in json.dumps(material_json)
                       and '"answers"' not in json.dumps(material_json))
            self.cli("locale-rule-" + locale, "rule-shadow-report", self.rule, locale=locale, as_json=False)
            self.cli("locale-verification-" + locale, "verifications", "verify", locale=locale, as_json=False)
            self.cli("locale-job-error-" + locale, "job-run", "missing", locale=locale, expected=2, error="JOB_NOT_FOUND")
            self.report["locale_checks"].append({"locale": locale, "passed": True})

    def delivery(self):
        first = self.cli("job-task", "run", "Synthetic queued generation", "--task-id", "queued")
        script = self.output / "generator.py"
        script.write_text("import json,sys\nvalue=json.load(sys.stdin)\nprint(json.dumps(value['proposal_template']))\n")
        adapter = self.document("adapter", {"argv": [sys.executable, str(script)]})
        for job in ("cancel-job", "proposal-job"):
            self.cli("job-submit-" + job, "job-submit", "queued", "--adapter", adapter,
                     "--expected-revision", first["state"]["revision"], "--key", job)
        self.cli("job-cancel", "job-cancel", "cancel-job", "--reason", "Synthetic cancellation")
        self.cli("job-list", "jobs")
        worked = self.cli("worker", "worker", "--max-jobs", "10")
        self.check("queued_proposal_recorded", worked["processed"][0]["status"] == "COMPLETED")
        for command in ("job-run", "job-recover"):
            result = self.cli(command, command, "proposal-job")
            self.check(command + "_does_not_repeat", result["duplicate"] is True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cross", required=True)
    parser.add_argument("--precedent", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists():
        print("Refusing to overwrite an existing output directory", file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=False)
    demo = ExtendedDemo(output, Path(args.cross).resolve(), Path(args.precedent).resolve())
    demo.report["format"] = "verantyx.extended-workflow.v1"
    try:
        demo.cli("setup", "setup", "--non-interactive", "--learning", "manual", "--max-items", "3")
        demo.governance()
        demo.verification()
        demo.learning()
        demo.delivery()
        demo.report.update(passed=True, cli_invocations=len(demo.commands))
    except Exception as error:
        demo.report["error"] = {"type": type(error).__name__, "message": str(error)}
    write_json(output / "commands.json", demo.commands)
    write_json(output / "report.json", demo.report)
    print(json.dumps({"passed": demo.report["passed"], "commands": len(demo.commands), "error": demo.report.get("error")}))
    return 0 if demo.report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
