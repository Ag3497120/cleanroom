"""Bounded local inference deadlines, independent of generated text."""
import ipaddress
from urllib.parse import urlsplit

LOCAL_DEFAULT = 1800
LOCAL_MAXIMUM = 7200


def is_local(value):
    if value.get("provider") == "ollama":
        return True
    if value.get("provider") != "openai_compatible":
        return False
    try:
        return ipaddress.ip_address(urlsplit(value.get("endpoint", "")).hostname).is_loopback
    except (ValueError, TypeError):
        return False


def default_timeout(provider, endpoint, cloud=120):
    return LOCAL_DEFAULT if is_local({"provider": provider, "endpoint": endpoint}) else cloud


def process_limit(command):
    return LOCAL_MAXIMUM + 5 if is_local(command.get("model_api", {})) else 600
