"""Host deadlines and native error framing, independent of generated content."""
from io import StringIO
from unittest import TestCase

from verantyx.agent_models import invocation_timeout
from verantyx.errors import LedgerError
from verantyx.model_observation import diagnostic, emit, parse


class ModelDeadlineContract(TestCase):
    def test_connection_deadline_has_cleanup_margin(self):
        for kind in ("codex_cli", "claude_cli", "model_api"):
            self.assertEqual(invocation_timeout({kind: {"timeout": 300}}), 305)
            self.assertEqual(invocation_timeout({kind: {"timeout": 600}}), 600)

    def test_explicit_host_cap_is_never_extended(self):
        self.assertEqual(invocation_timeout({"codex_cli": {"timeout": 300}}, 12), 12)
        self.assertEqual(invocation_timeout({}), 120)
        for invalid in (0, -1, True, 601, "120"):
            with self.assertRaises(LedgerError):
                invocation_timeout({}, invalid)

    def test_native_failure_survives_closed_error_channel(self):
        out = StringIO()
        safe = diagnostic(LedgerError("BRIDGE_TIMEOUT", {"reason": "CODEX_TIMEOUT",
                          "provider_body": "must not leak", "api_key": "secret"}))
        emit(out, {"kind": "error", **safe})
        event = parse(out.getvalue().rstrip().encode())
        self.assertEqual(event["code"], "BRIDGE_TIMEOUT")
        self.assertEqual(event["details"], {"reason": "CODEX_TIMEOUT"})
        self.assertNotIn("secret", out.getvalue())
