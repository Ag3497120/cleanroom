"""Tool grants are not keyword semantics; imports never confer human mastery."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from verantyx import config, work_tools
from verantyx.agent_runtime import _tool
from verantyx.cli import parse
from verantyx.errors import LedgerError


class ToolboxBoundary(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = config.defaults(self.root, "en")
        config.save(self.root, self.cfg, None)

    def test_commands_catalogue_is_real_and_existing_commands_survive(self):
        _, args = parse(["commands", "develop"])
        names = {row["command"] for row in args.catalogue}
        self.assertTrue({"develop", "notebook", "connections", "model-api-check", "toolbox"} <= names)

    def test_check_requires_explicit_sandbox(self):
        value = dict(work_tools.DEFAULT, checks={"test": {"argv": ["/usr/bin/true"], "timeout": 5}})
        with self.assertRaises(LedgerError):
            work_tools.configure(self.root, value, confirmed=True)

    def test_readonly_is_explicit_not_inferred_from_words(self):
        work_tools.configure(self.root, dict(work_tools.DEFAULT, write_candidates=False), confirmed=True)
        with work_tools.session(self.root):
            receipt = _tool(self.root, "run", 0,
                            {"id": "write", "tool": "write_candidate", "path": "x.txt", "text": "hello"},
                            [], {})
        self.assertEqual(receipt["status"], "REFUSED")
        self.assertEqual(receipt["reason"], "WORK_READ_ONLY")
        self.assertFalse((self.root / "x.txt").exists())

    def test_ungranted_mcp_never_starts_process(self):
        with work_tools.session(self.root) as session:
            with self.assertRaises(LedgerError):
                session.execute({"id": "x", "tool": "call_mcp", "path": "unknown/shell", "text": "{}"},
                                run_id="run", turn=0, scope=[], artifacts={})
            self.assertIsNone(session.worker)

    def test_model_arguments_cannot_widen_owner_scope(self):
        value = dict(work_tools.DEFAULT, mcp_servers={"browser": {
            "argv": ["/usr/bin/true"], "tools": ["navigate"],
            "argument_schemas": {"navigate": {"type": "object", "properties": {
                "url": {"type": "string", "pattern": "^https://example[.]com/"}}}},
            "env": {}, "timeout": 5}})
        work_tools.configure(self.root, value, confirmed=True)
        with work_tools.session(self.root) as session:
            with self.assertRaises(LedgerError):
                session.execute({"id": "x", "tool": "call_mcp", "path": "browser/navigate",
                                 "text": '{"url":"file:///private/data"}'},
                                run_id="run", turn=0, scope=[], artifacts={})
            self.assertIsNone(session.worker)

    def test_grant_changes_are_not_silently_accepted_midrun(self):
        with work_tools.session(self.root) as session:
            work_tools.configure(self.root, dict(work_tools.DEFAULT, write_candidates=False), confirmed=True)
            with self.assertRaises(LedgerError):
                session.unchanged()
