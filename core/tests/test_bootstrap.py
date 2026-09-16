import contextlib
import copy
import io
import json
import os
from pathlib import Path
import string
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from verantyx import config
from verantyx.cli import main
from verantyx.i18n import LANGUAGES, catalog


class Terminal(io.StringIO):
    def isatty(self):
        return True


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="verantyx-test-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)

    def cli(self, *arguments):
        env = dict(os.environ, LANG="en_US.UTF-8")
        env.pop("VERANTYX_LANG", None)
        return subprocess.run(
            [sys.executable, str(ROOT / "bin/verantyx"), "--project", str(self.project), *arguments],
            input="", text=True, capture_output=True, env=env, timeout=10,
        )

    def create(self, locale="ja"):
        result = self.cli("setup", "--non-interactive", "--lang", locale, "--json", "--name", "試験 中文 한국어 Español",
                          "--purpose", "判断と学びを残す", "--learning", "manual")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def test_catalogs_cover_the_same_messages_and_placeholders(self):
        reference = catalog("en")
        formatter = string.Formatter()
        for locale in LANGUAGES:
            with self.subTest(locale=locale):
                translated = catalog(locale)
                self.assertEqual(reference.keys(), translated.keys())
                for key in reference:
                    self.assertTrue(translated[key].strip())
                    fields = lambda value: {field for _, field, _, _ in formatter.parse(value) if field}
                    self.assertEqual(fields(reference[key]), fields(translated[key]), key)

    def test_all_five_tutorials_are_read_only_and_aliases_match(self):
        for locale in LANGUAGES:
            with self.subTest(locale=locale):
                direct = self.cli("tutorial", "--lang", locale, "--json")
                alias = self.cli("--tutorial", "--lang", locale, "--json")
                self.assertEqual(direct.returncode, 0, direct.stderr)
                self.assertEqual(direct.stdout, alias.stdout)
                result = json.loads(direct.stdout)
                self.assertEqual(result["locale"], locale)
                self.assertTrue(result["simulated"])
                self.assertIn("/", result["text"])
                self.assertEqual(result["model_calls"], 0)
                self.assertFalse(result["writes"])
        self.assertFalse((self.project / ".verantyx").exists())

    def test_non_terminal_start_never_waits_or_writes(self):
        result = self.cli("--json")
        self.assertEqual(result.returncode, 3)
        self.assertFalse(json.loads(result.stdout)["configured"])
        self.assertFalse((self.project / ".verantyx").exists())

    def test_five_locale_configuration_round_trips_and_read_commands(self):
        for locale in LANGUAGES:
            created = self.create(locale)
            before = config.config_path(self.project).read_bytes()
            for command in ("status", "config", "doctor"):
                read = self.cli(command, "--json")
                self.assertEqual(read.returncode, 0, read.stderr)
                value = json.loads(read.stdout)
                self.assertEqual(value["config"], created["config"])
                self.assertFalse(value["capabilities"]["agent_execution"])
            self.assertEqual(config.config_path(self.project).read_bytes(), before)

    def test_display_override_does_not_change_saved_language(self):
        self.create("ja")
        result = self.cli("status", "--lang", "es")
        self.assertIn("Estado del proyecto", result.stdout)
        self.assertEqual(config.load(self.project)[0]["ui"]["locale"], "ja")
        default = self.cli("--help")
        self.assertIn("使い方", default.stdout)

    def test_chinese_aliases_are_normalized(self):
        for code in ("zh", "zh_CN.UTF-8", "zh-Hans", "zh-TW"):
            result = self.cli("tutorial", "--lang", code, "--json")
            self.assertEqual(json.loads(result.stdout)["locale"], "zh-Hans")

    def test_invalid_commands_have_localized_stable_errors(self):
        for locale in LANGUAGES:
            result = self.cli("run", "--lang", locale, "--json")
            self.assertEqual(result.returncode, 2)
            body = json.loads(result.stdout)["error"]
            self.assertEqual(body["code"], "ARGUMENTS")
            self.assertEqual(body["message"], catalog(locale)["error.ARGUMENTS"])
        result = self.cli("--lang", "invalid", "--json")
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "LOCALE_UNSUPPORTED")

    def test_update_preserves_identity_and_original_bytes_in_backup(self):
        first = self.create()["config"]
        before = config.config_path(self.project).read_bytes()
        result = self.cli("setup", "--non-interactive", "--learning", "off", "--json")
        second = json.loads(result.stdout)["config"]
        self.assertEqual(first["project"], second["project"])
        self.assertEqual(second["learning"]["mode"], "off")
        backups = list((self.project / ".verantyx").glob("config.backup.*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        identical = self.cli("setup", "--non-interactive", "--json")
        self.assertFalse(json.loads(identical.stdout)["changed"])
        self.assertEqual(len(list((self.project / ".verantyx").glob("config.backup.*.json"))), 1)

    def test_malformed_and_future_configurations_cannot_be_overwritten(self):
        self.create()
        path = config.config_path(self.project)
        samples = [b"{broken", b'{"schema_version": 999}', b'{"schema_version": true}']
        for raw in samples:
            path.write_bytes(raw)
            result = self.cli("setup", "--non-interactive", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_bytes(), raw)
            help_result = self.cli("--help", "--lang", "ja")
            self.assertEqual(help_result.returncode, 0)
            self.assertIn("使い方", help_result.stdout)

    def test_invalid_settings_do_not_create_state(self):
        for arguments in (("--max-items", "0"), ("--max-items", "4"), ("--name", "")):
            result = self.cli("setup", "--non-interactive", "--json", *arguments)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((self.project / ".verantyx").exists())

    def test_stale_writer_is_rejected(self):
        self.create()
        value, previous = config.load(self.project)
        changed = copy.deepcopy(value)
        changed["project"]["purpose"] = "another writer's decision"
        config.save(self.project, changed, previous)
        with self.assertRaises(config.ConfigError) as error:
            config.save(self.project, value, previous)
        self.assertEqual(error.exception.code, "CONFIG_CHANGED")
        self.assertEqual(config.load(self.project)[0], changed)

    def test_configuration_lock_prevents_overwrite(self):
        self.create()
        value, previous = config.load(self.project)
        lock = self.project / ".verantyx/.config.lock"
        lock.write_text("another process", encoding="utf-8")
        with self.assertRaises(config.ConfigError) as error:
            config.save(self.project, value, previous)
        self.assertEqual(error.exception.code, "CONFIG_LOCKED")
        self.assertEqual(lock.read_text(), "another process")
        self.assertEqual(config.config_path(self.project).read_bytes(), previous)

    def test_failed_write_preserves_previous_configuration(self):
        self.create()
        value, previous = config.load(self.project)
        value["project"]["purpose"] = "new purpose"
        with patch("verantyx.config.exclusive_write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                config.save(self.project, value, previous)
        self.assertEqual(config.config_path(self.project).read_bytes(), previous)
        self.assertFalse((self.project / ".verantyx/.config.lock").exists())

    def test_symlink_configuration_does_not_modify_target(self):
        other = self.project / "external"
        other.mkdir()
        (self.project / ".verantyx").symlink_to(other, target_is_directory=True)
        result = self.cli("setup", "--non-interactive", "--json")
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "CONFIG_SYMLINK")
        self.assertEqual(list(other.iterdir()), [])

    def test_first_interactive_launch_uses_safe_defaults_after_consent(self):
        for locale in LANGUAGES:
            project = self.project / locale
            project.mkdir()
            with patch("sys.stdin", Terminal()), contextlib.redirect_stdout(Terminal()), \
                    patch("verantyx.session_commands.authorize_workspace", return_value=True) as consent, \
                    patch("verantyx.terminal_ui.capable_terminal", return_value=False), \
                    patch("verantyx.development_console.interact", return_value={"ok": True}) as interact:
                code = main(["--project", str(project), "--lang", locale])
            self.assertEqual(code, 0)
            consent.assert_called_once()
            value, _ = config.load(project)
            self.assertEqual(value["project"]["name"], project.name)
            self.assertEqual(value["ui"]["locale"], locale)
            self.assertTrue(interact.call_args.kwargs["onboarding"])

    def test_cancellation_and_eof_leave_no_incomplete_settings(self):
        for answers in (":q\n", "name\npurpose\n1\n1\n2\n", "name\n"):
            with patch("sys.stdin", Terminal(answers)), contextlib.redirect_stdout(Terminal()), contextlib.redirect_stderr(io.StringIO()):
                code = main(["--project", str(self.project), "--lang", "ja"])
            self.assertEqual(code, 130)
            self.assertFalse((self.project / ".verantyx").exists())


if __name__ == "__main__":
    unittest.main()
