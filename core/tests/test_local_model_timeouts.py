"""Local thinking gets its configured deadline at every process boundary."""
from pathlib import Path
import tempfile
from unittest import TestCase

from verantyx.agent_models import create_api_profile, invocation_timeout
from verantyx.adapters.command_process import BoundedProcess, load_command
from verantyx.model_api import load_config, validate_config
from verantyx.model_timeouts import default_timeout
from verantyx.model_usage import normalize
from verantyx.errors import LedgerError


class LocalTimeoutTests(TestCase):
    def test_changing_existing_timeout_keeps_reasoning_and_old_profile(self):
        from verantyx import config
        from verantyx.agent_models import activate_work_api, selected_work
        from verantyx.domain.codec import canonical
        from verantyx.model_preferences import set_timeout
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            (root / ".verantyx").mkdir()
            cfg = config.defaults(root, "ja")
            config.save(root, cfg, None)
            activate_work_api(root, cfg, provider="ollama", model="test",
                              endpoint="http://127.0.0.1:11434/api/chat", allow_loopback_http=True)
            original = Path(selected_work(root, cfg))
            value = {**load_config(original), "thinking": True, "context_window": 32768}
            original.write_text(canonical(value))
            set_timeout(root, cfg, 3600)
            updated = Path(selected_work(root, cfg))
            self.assertNotEqual(original, updated)
            self.assertEqual(load_config(original), value)
            self.assertEqual(load_config(updated), {**value, "timeout": 3600})

    def test_local_defaults_and_outer_cleanup_margin(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / ".verantyx").mkdir()
            for provider, path in (("ollama", "/api/chat"), ("openai_compatible", "/v1/chat/completions")):
                directory = create_api_profile(root, provider=provider, model="test",
                    endpoint="http://127.0.0.1:11434" + path, allow_loopback_http=True)
                adapter = directory / "implementation.json"
                cfg = load_config(adapter)
                self.assertEqual(cfg["timeout"], 1800)
                command = load_command(adapter)
                self.assertEqual(invocation_timeout(command), 1805)
                self.assertEqual(BoundedProcess(command, timeout=invocation_timeout(command)).timeout, 1805)
                self.assertEqual(invocation_timeout(command, 5), 5)
                self.assertEqual(validate_config({**cfg, "timeout": 7200})["timeout"], 7200)
                for invalid in (0, True, 7201):
                    with self.assertRaises(LedgerError):
                        validate_config({**cfg, "timeout": invalid})

    def test_remote_and_non_model_processes_keep_their_existing_limits(self):
        self.assertEqual(default_timeout("openai", "https://api.openai.com/v1/responses"), 120)
        self.assertEqual(default_timeout("openai_compatible", "https://example.org/v1/chat/completions"), 120)
        with self.assertRaises(LedgerError):
            BoundedProcess({}, timeout=1805)
        with self.assertRaises(LedgerError):
            invocation_timeout({}, 1800)

    def test_ollama_counts_are_reported_without_inventing_cache_hits(self):
        result = normalize("ollama", {"prompt_eval_count": 80, "eval_count": 20})
        self.assertEqual(result, {"input_tokens": 80, "output_tokens": 20})
        self.assertNotIn("cached_input_tokens", result)
