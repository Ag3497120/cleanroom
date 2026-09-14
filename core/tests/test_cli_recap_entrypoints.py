"""CLI navigation is model-free; role and authority remain separate."""
import contextlib
import io
import json
import unittest
from unittest import mock

import test_responses_v06 as fixtures
from verantyx.cli import main, parse
from verantyx.console import dictionary_arguments
from verantyx.errors import LedgerError
from verantyx.storage.sqlite import EventStore


class Terminal(io.StringIO):
    def isatty(self):
        return True


class RecapEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ResponseTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--project", str(self.root), "--lang", "ja", *args])
        return code, output.getvalue()

    def test_recap_reads_recorded_state_without_model_or_new_events(self):
        self.fixture.start("recorded")
        with EventStore(self.root, self.fixture.cfg["project"]["id"]) as store:
            before = store.events()
        with mock.patch("subprocess.Popen", side_effect=AssertionError("external process")), \
                mock.patch("socket.socket", side_effect=AssertionError("network")):
            code, output = self.cli("recap", "recorded", "--json")
        self.assertEqual(code, 0, output)
        result = json.loads(output)
        self.assertEqual((result["command"], result["run_id"]), ("recap", "recorded"))
        self.assertFalse(result["writes"])
        self.assertFalse(result["model_called"])
        self.assertFalse(result["ownership"]["authority_granted"])
        with EventStore(self.root, self.fixture.cfg["project"]["id"]) as store:
            self.assertEqual(before, store.events())
        self.assertEqual(self.fixture.invocations(), [])

    def test_unsigned_recap_does_not_require_mutation_permission(self):
        self.fixture.start("recorded")
        with mock.patch("verantyx.authority.state", return_value={"enabled": True}):
            code, output = self.cli("recap", "recorded")
        self.assertEqual(code, 0, output)
        self.assertIn("BUILD:", output)
        self.assertIn("EVIDENCE:", output)
        self.assertIn("OWNERSHIP:", output)
        self.assertNotIn("\x1b", output)

    def test_missing_run_returns_domain_error_not_success(self):
        code, output = self.cli("recap", "missing", "--json")
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(output)["error"]["code"], "RUN_NOT_FOUND")

    def test_help_and_parser_expose_small_views(self):
        _, args = parse(["recap", "recorded"])
        self.assertEqual(args.run_id, "recorded")
        code, output = self.cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("verantyx recap RUN_ID", output)
        self.assertIn("dictionary --view delegate", output)

    def test_dictionary_free_text_is_not_split_into_extra_positionals(self):
        self.assertEqual(dictionary_arguments("/dictionary retry idempotence"),
                         ["dictionary", "retry idempotence"])
        self.assertEqual(dictionary_arguments("/dictionary --view learn retry idempotence"),
                         ["dictionary", "--view", "learn", "retry idempotence"])
        self.assertEqual(dictionary_arguments("/dictionary"), ["dictionary"])
        for request in ("/dictionary --view", "/dictionary --view execute"):
            with self.assertRaises(LedgerError):
                dictionary_arguments(request)

    def test_interactive_read_commands_do_not_call_model(self):
        self.fixture.start("recorded")
        adapter = self.fixture.adapter()
        output = Terminal()
        commands = "/recap\n/recap recorded\n/dictionary --view learn\n/dictionary --view delegate\n/help\n/quit\n"
        with mock.patch("sys.stdin", Terminal(commands)), contextlib.redirect_stdout(output):
            code = main(["--project", str(self.root), "--lang", "ja", "start",
                         "--plain", "--adapter", str(adapter)])
        self.assertEqual(code, 0)
        self.assertIn("BUILD:", output.getvalue())
        self.assertIn("/recap [RUN_ID]", output.getvalue())
        self.assertEqual(self.fixture.invocations(), [])


if __name__ == "__main__":
    unittest.main()
