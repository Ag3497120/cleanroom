"""Produce a reviewable result from the real test suite, not a hand-entered test count."""
from pathlib import Path
import datetime
import io
import json
import os
import platform
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / "src"), str(root / "tests")]
# Child-process tests must load the same source checkout as the parent runner.
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (str(root / "src"), os.environ.get("PYTHONPATH"))))
suite = unittest.defaultTestLoader.discover(str(root / "tests"))
output = io.StringIO()
result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
(root / "validation/test-output.txt").write_text(output.getvalue())
from verantyx.adapters.cross_policy import CrossPolicyBackend
from verantyx.adapters.precedent_backend import PrecedentBackend
report = {"recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "python": sys.version,
          "platform": platform.platform(), "tests_run": result.testsRun, "passed": result.wasSuccessful(),
          "failures": [name.id() for name, _ in result.failures], "errors": [name.id() for name, _ in result.errors],
          "skipped": [(name.id(), reason) for name, reason in result.skipped],
          "cross": CrossPolicyBackend().identity,
          "precedent": PrecedentBackend(os.environ["VERANTYX_PRECEDENT"]).identity,
          "live_model_calls": 0, "fixtures_only": True}
from verantyx import __version__
report["version"] = __version__
report["test_modules"] = sorted(path.name for path in (root / "tests").glob("test_*.py"))
report["mcp_test_scope"] = "temporary HOME and separate fixture memory; no production memory writes"
(root / "validation/results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({k: report[k] for k in ("tests_run", "passed", "failures", "errors", "skipped")}))
sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
