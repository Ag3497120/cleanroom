"""UI text only: localized labels never determine permissions or state."""
from functools import lru_cache
from importlib.resources import files
import json
import os

LANGUAGES = {"en": "English", "ja": "日本語", "zh-Hans": "简体中文", "ko": "한국어", "es": "Español"}


def normalize(value: str) -> str:
    name = value.strip().replace("_", "-").split(".")[0].split("@")[0].lower()
    if name in ("c", "posix"):
        return "en"
    prefix = name.split("-")[0]
    if prefix == "zh":
        return "zh-Hans"
    if prefix in LANGUAGES:
        return prefix
    raise ValueError("unsupported locale")


def environment_locale() -> str:
    for key in ("VERANTYX_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        if os.environ.get(key):
            try:
                return normalize(os.environ[key])
            except ValueError:
                return "en"
    return "en"


@lru_cache(maxsize=5)
def catalog(locale: str) -> dict[str, str]:
    return json.loads(files("verantyx").joinpath("locales", f"{locale}.json").read_text(encoding="utf-8"))


def text(locale: str, key: str, **values) -> str:
    return catalog(locale)[key].format(**values)
