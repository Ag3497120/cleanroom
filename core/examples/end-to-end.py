#!/usr/bin/env python3
"""Run the real CLI in a new, inspectable artificial project.

Example (requires the existing Cross VM and Precedent executor):
  python3 examples/end-to-end.py --output /new/demo \
      --cross /path/to/cross --precedent /path/to/precedent

Optional real MCP round trip, isolated from production memory:
  --vera-source /path/to/call-me-vera --vera-python /path/to/venv/bin/python

The two proposal adapters are deterministic local fixtures. No LLM is called,
and the scripted decisions/learning submissions are never the user's choices.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid

LANGUAGES = ("en", "ja", "zh-Hans", "ko", "es")
NEW_COMMANDS = (
    "learn-collect", "learn-raise", "learn-target", "learn-defer", "learn-resume",
    "learn-explain", "learn-counterexample", "learn-apply", "learn-transfer",
    "adoption-propose", "adoption-review", "adoption-authorize", "adopt", "propose",
    "handoff-packet", "memory-save", "memory-start", "memory-read", "memory-search",
    "memory-lookup", "memory-digest-lookup",
)
PRIVATE_REQUEST = "ARTIFICIAL_REQUEST_DO_NOT_EXPORT"
PRIVATE_PROPOSAL = "ARTIFICIAL_PROPOSAL_DO_NOT_EXPORT"
PRIVATE_RESPONSE = "ARTIFICIAL_LEARNING_RESPONSE_DO_NOT_EXPORT"
PRIVATE_FILE = "ARTIFICIAL_PRIVATE_FILE_DO_NOT_EXPORT"
GOOD_SOURCE = "def add(a, b):\n    return a + b\n"
SCOPE = ("--component", "writer", "--workload", "parallel", "--risk", "HIGH")


class DemoFailure(RuntimeError):
    pass


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


class Demo:
    def __init__(self, output, cross, precedent):
        self.output, self.cross, self.precedent = output, cross, precedent
        self.project = output / "project"
        self.project.mkdir()
        self.receipts = output / "receipts"
        self.receipts.mkdir()
        self.environment = {**os.environ, "VERANTYX_CROSS": str(cross),
                            "VERANTYX_PRECEDENT": str(precedent), "PYTHONDONTWRITEBYTECODE": "1"}
        source = Path(__file__).resolve().parents[1] / "src"
        if (source / "verantyx").is_dir():
            self.environment["PYTHONPATH"] = str(source)
        self.commands = []
        self.report = {"format": "verantyx.end-to-end-demo.v1", "passed": False,
                       "recorded_at": datetime.now(timezone.utc).isoformat(),
                       "fixtures_only": True, "live_model_calls": 0,
                       "human_decisions": "SCRIPTED_ARTIFICIAL_FIXTURE_NOT_USER_APPROVAL",
                       "learning_responses": "SCRIPTED_SELF_REPORT_NOT_VERIFIED_MASTERY",
                       "project": str(self.project), "checks": [], "negative_controls": {},
                       "dependencies": {"python": sys.executable, "cross": str(cross),
                                        "precedent": str(precedent)}, "locale_checks": []}

    def check(self, name, condition, **details):
        self.report["checks"].append({"name": name, "passed": bool(condition), **details})
        if not condition:
            raise DemoFailure(name)

    def cli(self, label, *arguments, locale="ja", expected=0, as_json=True, error=None):
        argv = [sys.executable, "-m", "verantyx", "--project", str(self.project), "--lang", locale]
        if as_json:
            argv.append("--json")
        argv.extend(str(item) for item in arguments)
        completed = subprocess.run(argv, env=self.environment, cwd=self.output,
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90)
        index = len(self.commands) + 1
        filename = f"{index:03d}-{label}.json"
        value = None
        if as_json:
            try:
                value = json.loads(completed.stdout)
            except json.JSONDecodeError:
                pass
        write_json(self.receipts / filename, {"arguments": argv, "returncode": completed.returncode,
                   "result": value, "stdout": completed.stdout if value is None else None, "stderr": completed.stderr})
        self.commands.append({"label": label, "locale": locale, "arguments": list(map(str, arguments)),
                              "json": as_json, "exit_code": completed.returncode, "receipt": "receipts/" + filename})
        if completed.returncode != expected or (as_json and type(value) is not dict):
            raise DemoFailure(f"{label}: expected exit {expected}, got {completed.returncode}; see receipts/{filename}")
        if "Traceback" in completed.stderr or "KeyError" in completed.stderr:
            raise DemoFailure(f"{label}: unhandled exception; see receipts/{filename}")
        if error is not None and (value or {}).get("error", {}).get("code") != error:
            raise DemoFailure(f"{label}: expected error {error}; see receipts/{filename}")
        return value if as_json else completed.stdout

    def git(self, *arguments):
        argv = ["git", "-C", str(self.project), "-c", "core.hooksPath=/dev/null",
                "-c", "core.fsmonitor=false", "-c", "commit.gpgSign=false", *arguments]
        return subprocess.run(argv, env=self.environment, check=True, capture_output=True, timeout=30).stdout

    def prepare(self):
        self.git("init", "-q", "--initial-branch=main")
        (self.project / ".gitignore").write_text(".verantyx/\n", encoding="utf-8")
        (self.project / "calc.py").write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
        (self.project / "notes.txt").write_text("committed baseline\n", encoding="utf-8")
        (self.project / "test_calc.py").write_text(
            "import unittest\nfrom calc import add\nclass Check(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
            "        self.assertEqual(add(-3, 2), -1)\n        self.assertEqual(add(0, 0), 0)\n", encoding="utf-8")
        self.git("add", ".gitignore", "calc.py", "notes.txt", "test_calc.py")
        self.git("-c", "user.name=Verantyx artificial fixture", "-c", "user.email=fixture@invalid",
                 "commit", "-qm", "Artificial fixture base")
        (self.project / "notes.txt").write_text("artificial staged unfinished work\n", encoding="utf-8")
        self.git("add", "notes.txt")
        (self.project / "notes.txt").write_text("artificial staged and unstaged unfinished work\n", encoding="utf-8")
        (self.project / "calc.py").write_text("# " + PRIVATE_FILE + "\ndef add(a, b):\n    return 0\n", encoding="utf-8")
        (self.project / "scratch.txt").write_text("untracked unfinished work\n", encoding="utf-8")
        self.before_files = {name: (self.project / name).read_bytes() for name in
                             (".gitignore", "calc.py", "notes.txt", "test_calc.py", "scratch.txt")}
        self.before_index = self.git("ls-files", "--stage", "-z")
        self.before_index_bytes = (self.project / ".git/index").read_bytes()
        self.before_head = self.git("rev-parse", "HEAD").decode().strip()
        self.cli("setup", "setup", "--non-interactive", "--name", "Artificial end-to-end fixture",
                 "--learning", "manual", "--max-items", "3")
        proposer = self.output / "artificial-proposer.py"
        proposer.write_text('''import json, os, sys
from pathlib import Path
value = json.load(sys.stdin)
task = value["task"]
provider = os.environ["DEMO_PROVIDER"]
capture = Path(os.environ["DEMO_CAPTURE"])
capture.mkdir(exist_ok=True)
(capture / (task["task_id"] + ".json")).write_text(json.dumps(value, ensure_ascii=False))
document = {"schema_version": 1, "task_id": task["task_id"],
            "context_revision": task["context_revision"], "response_locale": task["response_locale"],
            "summary": "ARTIFICIAL_PROPOSAL_DO_NOT_EXPORT: deterministic fixture " + provider,
            "claims": [], "actions": [], "unknowns": [],
            "decision_points": [{"id": "separation", "kind": "VALUE_DECISION", "decision_type": "parallel_writers",
                "question": "Artificial fixture: isolate writers?", "options": [
                    {"id": "isolate", "label": "Separate worktrees"}, {"id": "shared", "label": "Shared working files"}]}]}
if task["task_id"] != "decision":
    document["actions"] = [{"id": "writer", "tool_id": "writer.apply", "arguments": {
        "point_id": "separation", "destination": "shared",
        "files": {"calc.py": "def add(a, b):\\n    return a + b\\n"}, "tests": ["test_calc.py"]},
        "reason": "Artificial candidate to be tested in a separate worktree", "source_refs": []}]
json.dump(document, sys.stdout, ensure_ascii=False)
sys.stdout.write("\\n")
''', encoding="utf-8")
        self.adapters = {}
        for provider in ("A", "B"):
            path = self.output / f"adapter-{provider}.json"
            write_json(path, {"argv": [sys.executable, str(proposer)], "env": {
                "DEMO_PROVIDER": provider, "DEMO_CAPTURE": str(self.output / "adapter-inputs"),
                "PYTHONDONTWRITEBYTECODE": "1"}})
            self.adapters[provider] = path

    def propose_run(self, run_id, provider="B", locale="ja"):
        started = self.cli("run-" + run_id, "run", PRIVATE_REQUEST + ": " + run_id,
                           "--task-id", run_id, "--observe", "calc.py", *SCOPE, "--key", "run-" + run_id, locale=locale)
        generated = self.cli("propose-" + run_id, "propose", run_id, "--adapter", self.adapters[provider],
                             "--key", "propose-" + run_id, "--expected-revision", started["recorded_revision"],
                             "--include", "calc.py", locale=locale)
        return generated

    def raise_learning(self, run_id, source_ref):
        return self.cli("raise-" + run_id, "learn-raise", run_id, "--key", "raise-" + run_id,
            "--concept", "worktree separation", "--concept-id", "parallel_writers",
            "--why-now", "Artificial fixture: preserve unfinished parallel edits",
            "--minimum-model", "A branch separates references; a worktree separates files and its index.",
            "--counterexample", "Two writers switch branches inside the same unfinished directory.",
            "--check", "Describe a setup that preserves both writers' unfinished files.", "--source-ref", source_ref)

    def workflow(self):
        first = self.propose_run("decision", "A")
        self.check("first_run_asks_one_human_decision", first["state"]["assessment"]["question"] is not None)
        decided = self.cli("human-decision", "decide", "decision", "--point", "separation", "--choice", "isolate",
                           "--reason", "Artificial fixture decision, not user approval", "--key", "human-decision")
        case_id = decided["precedent_id"]
        self.cli("precedent-accept", "precedent-accept", case_id, "--key", "accept-case")
        drafted = self.cli("rule-draft", "rule-draft", case_id, "--key", "draft-rule")
        rule_id = drafted["rule_id"]
        for operation in ("rule-shadow", "rule-confirm", "rule-activate"):
            self.cli(operation, operation, rule_id, "--key", operation)
        self.report["precedent_id"], self.report["rule_id"] = case_id, rule_id
        second = self.propose_run("candidate")
        assessment = second["state"]["assessment"]
        self.check("second_run_reuses_rule_without_reasking", assessment["question"] is None and
                   assessment["judgments"][0]["status"] == "PRECEDENT_MATCHED")
        self.check("proposal_adapter_is_replaceable", first["executor_sha256"] != second["executor_sha256"])
        lease = self.cli("authorize-candidate", "authorize", "candidate", "--action", "writer", "--ttl", "600",
                         "--precedent", self.precedent, "--key", "authorize-candidate")
        lease_id = lease["lease_id"]
        raised = self.raise_learning("candidate", second["state"]["request_ref"])
        candidate_id = raised["candidate_id"]
        common = ("candidate", "--candidate", candidate_id)
        self.cli("learning-collect", "learn-collect", *common, "--key", "learning-collect")
        self.cli("learning-target", "learn-target", *common, "--target", "REVIEW",
                 "--reason", "Artificial fixture ownership target", "--key", "learning-target")
        self.cli("learning-defer", "learn-defer", *common, "--reason", "Artificial fixture: continue project first", "--key", "defer")
        self.cli("learning-resume", "learn-resume", *common, "--reason", "Artificial fixture: revisit the principle", "--key", "learn-resume")
        for operation in ("explain", "counterexample", "apply", "transfer"):
            self.cli("learning-" + operation, "learn-" + operation, *common,
                     "--statement", PRIVATE_RESPONSE + ": " + operation, "--key", "learning-" + operation)
        executed = self.cli("execute-candidate", "execute", "candidate", "--lease", lease_id,
                            "--precedent", self.precedent, "--key", "execute-candidate")
        effect = executed["execution"]
        self.check("learning_does_not_invalidate_execution_permission", effect["status"] == "CANDIDATE_TESTED")
        self.check("actual_precedent_tests_pass", effect["receipt"]["verification"]["result"]["passed"])
        self.check("candidate_is_in_separate_worktree", Path(effect["receipt"]["worktree"]) != self.project)
        self.report["execution"] = {"lease_id": lease_id, "status": effect["status"],
                                    "worktree": effect["receipt"]["worktree"],
                                    "verification": effect["receipt"]["verification"]}
        adoption = self.cli("adoption-propose", "adoption-propose", "candidate", "--lease", lease_id,
                            "--precedent", self.precedent, "--message", "Artificial fixture: adopt tested addition",
                            "--key", "adoption-propose")
        adoption_id = adoption["adoption_id"]
        self.cli("adopt-without-permission", "adopt", "candidate", "--adoption", adoption_id,
                 "--precedent", self.precedent, "--key", "adopt-before-permission", expected=2, error="ADOPTION_STAGE")
        self.report["negative_controls"]["adopt_without_permission"] = "ADOPTION_STAGE"
        review = self.cli("adoption-review", "adoption-review", "candidate", "--adoption", adoption_id, "--precedent", self.precedent)
        self.check("adoption_review_contains_concrete_diff", any("+    return a + b" in change["diff"] for change in review["changes"]))
        self.cli("adoption-authorize", "adoption-authorize", "candidate", "--adoption", adoption_id,
                 "--reason", "Artificial fixture adoption approval, not user approval", "--ttl", "600",
                 "--precedent", self.precedent, "--key", "adoption-permission")
        adopted = self.cli("adopt", "adopt", "candidate", "--adoption", adoption_id,
                           "--precedent", self.precedent, "--key", "adopt")
        self.check("canonical_adoption_completed", adopted["adoption"]["status"] == "ADOPTED")
        self.report["adoption"] = {"id": adoption_id, **adopted["adoption"]["receipt"]}
        self.check("git_show_contains_adopted_code", self.git("show", "verantyx/canonical:calc.py").decode() == GOOD_SOURCE)
        self.check("canonical_branch_matches_receipt", self.git("rev-parse", "verantyx/canonical").decode().strip() ==
                   adopted["adoption"]["receipt"]["commit"])
        self.check("adoption_excludes_unfinished_staged_work", self.git("show", "verantyx/canonical:notes.txt") == b"committed baseline\n")
        learned = self.cli("learn", "learn", "candidate")
        item = next(item for item in learned["candidates"] if item["id"] == candidate_id)
        self.check("learning_is_self_report_and_never_certified", len(item["evidence"]) == 4 and
                   item["mastery_evidence"] == "SELF_REPORTED" and item["externally_verified"] is False and item["assessment"] is None)
        self.report["learning"] = {key: item[key] for key in ("id", "status", "cycle", "ownership_target", "submission_state",
                                                             "mastery_evidence", "mastery_assessment", "externally_verified")}
        self.report["learning"]["evidence_count"] = len(item["evidence"])
        self.stale_control()
        return candidate_id, adoption_id

    def stale_control(self):
        view = self.propose_run("stale-control")
        lease = self.cli("authorize-stale", "authorize", "stale-control", "--action", "writer",
                         "--precedent", self.precedent, "--key", "authorize-stale")
        candidate_id = self.raise_learning("stale-control", view["state"]["request_ref"])["candidate_id"]
        self.cli("non-learning-resume", "resume", "stale-control", "--key", "refresh-context")
        self.cli("learning-after-context-change", "learn-target", "stale-control", "--candidate", candidate_id,
                 "--target", "REFERENCE", "--reason", "Artificial fixture: preserve earlier context invalidation", "--key", "later-learning")
        stale = self.cli("execute-stale", "execute", "stale-control", "--lease", lease["lease_id"],
                         "--precedent", self.precedent, "--key", "execute-stale", expected=4)
        self.check("non_learning_change_still_invalidates_permission", stale["execution"]["status"] == "INVALIDATED"
                   and stale["execution"]["reason"] == "CONTEXT_CHANGED")
        target = self.project / ".verantyx/worktrees" / lease["lease_id"]
        self.check("stale_permission_created_no_worktree", not target.exists())
        self.report["negative_controls"]["learning_then_resume_then_learning"] = {
            "status": stale["execution"]["status"], "reason": stale["execution"]["reason"], "worktree_created": target.exists()}

    def locale_checks(self, candidate_id, adoption_id):
        for locale in LANGUAGES:
            self.cli("locale-learn-" + locale, "learn", "candidate", locale=locale)
            self.cli("locale-display-" + locale, "learn", "candidate", locale=locale, as_json=False)
            self.cli("locale-adoption-" + locale, "adoption-review", "candidate", "--adoption", adoption_id,
                     "--precedent", self.precedent, locale=locale)
            self.cli("locale-packet-" + locale, "handoff-packet", "candidate", locale=locale)
            self.cli("locale-learning-error-" + locale, "learn-target", "candidate", "--candidate", "missing",
                     "--target", "OWN", "--reason", "Artificial error fixture", "--key", "missing-" + locale,
                     locale=locale, expected=2, error="LEARNING_NOT_FOUND")
            self.cli("locale-adoption-error-" + locale, "adoption-review", "candidate", "--adoption", "missing",
                     "--precedent", self.precedent, locale=locale, expected=2, error="ADOPTION_STAGE")
            self.cli("locale-memory-error-" + locale, "memory-start", "--server", self.output / "unused.json",
                     "--name", "../invalid", locale=locale, expected=2, error="MEMORY_NAME_REQUIRED")
            for command in NEW_COMMANDS:
                self.cli("locale-arguments-" + locale + "-" + command, command,
                         locale=locale, expected=2, error="ARGUMENTS")
            self.report["locale_checks"].append({"locale": locale, "passed": True,
                "json_success": ["learn", "adoption-review", "handoff-packet"], "text_success": ["learn"],
                "domain_errors": ["LEARNING_NOT_FOUND", "ADOPTION_STAGE", "MEMORY_NAME_REQUIRED"],
                "argument_errors": list(NEW_COMMANDS)})

    def handoff(self, vera_source=None, vera_python=None):
        packet_path = self.output / "handoff.json"
        packet = self.cli("handoff-packet", "handoff-packet", "decision", "candidate", "stale-control", "--output", packet_path)
        text = packet_path.read_text(encoding="utf-8")
        self.check("handoff_excludes_raw_artificial_private_text", all(value not in text for value in
                   (PRIVATE_REQUEST, PRIVATE_PROPOSAL, PRIVATE_RESPONSE, PRIVATE_FILE)))
        self.check("handoff_keeps_reference_only_boundary", packet["packet"]["authority"] == "REFERENCE_ONLY"
                   and packet["packet"]["automatic_conversation_collection"] is False)
        self.report["handoff"] = {"path": str(packet_path), "file_sha256": packet["file_sha256"],
                                  "packet_sha256": packet["packet"]["packet_sha256"]}
        if vera_source is None:
            self.report["memory"] = {"performed": False, "reason": "No isolated Vera source was selected."}
            return
        memory_home = self.output / "memory-home"
        memory_home.mkdir()
        name = "verantyx-demo-" + uuid.uuid4().hex
        server = self.output / "isolated-vera-server.json"
        write_json(server, {"argv": [str(vera_python), "-m", "vera.cli", "mcp", "--store", str(memory_home / "default.db")],
                            "cwd": str(vera_source), "env": {"HOME": str(memory_home), "PYTHONPATH": str(vera_source),
                                                               "PYTHONDONTWRITEBYTECODE": "1"}})
        common = ("--server", server, "--name", name)
        self.cli("memory-start", "memory-start", *common)
        self.cli("memory-reject-changed-packet", "memory-save", packet_path, "--expected-sha256", "0" * 64,
                 *common, "--key", "invalid-packet", expected=2, error="MEMORY_PACKET_CHANGED")
        self.report["negative_controls"]["changed_handoff_packet"] = "MEMORY_PACKET_CHANGED"
        saved = self.cli("memory-save", "memory-save", packet_path, "--expected-sha256", packet["file_sha256"],
                         *common, "--key", "memory-save")
        duplicate = self.cli("memory-save-retry", "memory-save", packet_path, "--expected-sha256", packet["file_sha256"],
                             *common, "--key", "memory-save")
        read = self.cli("memory-read", "memory-read", *common, "--limit", "100", "--max-chars", "60000")
        entries = read["result"]["entries"]
        self.check("real_mcp_saved_only_selected_demo_memory", saved["receipt"]["memory"]["name"] == name
                   and (memory_home / ".vera/stores" / (name + ".db")).is_file())
        self.check("mcp_retry_does_not_duplicate_records", duplicate["duplicate"] is True and len(entries) == 6)
        self.check("mcp_read_contains_reviewed_packet", packet["packet"]["packet_sha256"] in json.dumps(entries))
        self.check("mcp_read_excludes_raw_artificial_private_text", all(value not in json.dumps(entries) for value in
                   (PRIVATE_REQUEST, PRIVATE_PROPOSAL, PRIVATE_RESPONSE, PRIVATE_FILE)))
        self.cli("memory-search", "memory-search", packet["packet"]["packet_sha256"], *common)
        self.cli("memory-lookup", "memory-lookup", "1", *common)
        self.report["memory"] = {"performed": True, "name": name, "home": str(memory_home), "entries": len(entries),
                                  "reference_only": True, "production_memory_used": False, "server_configuration": str(server)}

    def finish_checks(self):
        self.check("original_working_files_preserved", all((self.project / name).read_bytes() == value for name, value in self.before_files.items()))
        self.check("staged_index_entries_preserved", self.git("ls-files", "--stage", "-z") == self.before_index)
        self.check("index_file_bytes_preserved", (self.project / ".git/index").read_bytes() == self.before_index_bytes)
        self.check("checked_out_head_preserved", self.git("rev-parse", "HEAD").decode().strip() == self.before_head)
        self.report["preservation"] = {"head": self.before_head, "index_sha256": sha256(self.before_index_bytes),
                                       "files_sha256": {name: sha256(value) for name, value in self.before_files.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", required=True, help="A new directory; existing paths are always refused.")
    parser.add_argument("--cross", default=os.environ.get("VERANTYX_CROSS"))
    parser.add_argument("--precedent", default=os.environ.get("VERANTYX_PRECEDENT"))
    parser.add_argument("--vera-source", default=os.environ.get("VERANTYX_VERA_SOURCE"))
    parser.add_argument("--vera-python", default=os.environ.get("VERANTYX_VERA_PYTHON"))
    parser.add_argument("--skip-memory", action="store_true", help="Explicitly omit the optional isolated MCP round trip.")
    args = parser.parse_args(argv)
    if not args.cross or not args.precedent:
        parser.error("Choose --cross and --precedent, or set VERANTYX_CROSS and VERANTYX_PRECEDENT.")
    cross, precedent = Path(args.cross).expanduser().resolve(), Path(args.precedent).expanduser().resolve()
    if not cross.is_file() or not (precedent / "precedent/execution.py").is_file():
        parser.error("The selected Cross executable or Precedent execution module is missing.")
    vera_source = None if args.skip_memory or not args.vera_source else Path(args.vera_source).expanduser().resolve()
    vera_python = None
    if vera_source is not None:
        vera_python = Path(args.vera_python).expanduser().absolute() if args.vera_python else vera_source / ".venv/bin/python"
        if not vera_source.is_dir() or not vera_python.is_file():
            parser.error("The selected isolated Vera source or Python interpreter is missing.")
    output = Path(args.output).expanduser().absolute()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print("Refusing to overwrite an existing output path: " + str(output), file=sys.stderr)
        return 2
    demo = Demo(output.resolve(), cross, precedent)
    try:
        demo.prepare()
        candidate_id, adoption_id = demo.workflow()
        demo.locale_checks(candidate_id, adoption_id)
        demo.handoff(vera_source, vera_python)
        demo.finish_checks()
        demo.report["passed"] = True
    except (DemoFailure, OSError, KeyError, ValueError, subprocess.SubprocessError) as problem:
        demo.report["error"] = {"type": type(problem).__name__, "message": str(problem)}
    write_json(output / "commands.json", demo.commands)
    demo.report["cli_commands"] = len(demo.commands)
    write_json(output / "report.json", demo.report)
    print(json.dumps({"passed": demo.report["passed"], "report": str(output / "report.json"),
                      "fixtures_only": True, "live_model_calls": 0}, ensure_ascii=False))
    return 0 if demo.report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
