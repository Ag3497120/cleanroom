"""Deterministic conservative path comparison for protected project files."""
from unicodedata import normalize


def portable_path_key(path):
    """Compare validated paths without consulting the replay host's filesystem.

    Canonical Unicode spellings and case variants are treated as the same name,
    including on filesystems that could store those spellings separately. This
    is a protection rule, not path validation or a claim of physical identity.
    """
    return normalize("NFC", normalize("NFC", path).casefold())
