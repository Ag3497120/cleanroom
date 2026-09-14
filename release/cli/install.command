#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    printf '%s\n' 'This preview bundle requires macOS on Apple Silicon.' >&2
    exit 1
fi
cd "$ROOT"
/usr/bin/shasum -a 256 -c checksums.sha256
PYTHON=${VERANTYX_PYTHON:-}
if [ -z "$PYTHON" ]; then
    for candidate in python3.14 python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3,11))' 2>/dev/null; then
            PYTHON=$(command -v "$candidate")
            break
        fi
    done
fi
if [ -z "$PYTHON" ] || ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3,11))'; then
    printf '%s\n' 'Python 3.11 or newer is required. Set VERANTYX_PYTHON to its executable path.' >&2
    exit 1
fi
if [ -L .venv ]; then
    printf '%s\n' 'Refusing a symbolic-link installation directory.' >&2
    exit 1
fi
if [ ! -e .venv ]; then
    "$PYTHON" -m venv .venv
elif [ ! -x .venv/bin/python ]; then
    printf '%s\n' 'An incomplete .venv already exists. Choose a fresh extracted bundle.' >&2
    exit 1
fi
set -- "$ROOT"/wheelhouse/verantyx-*.whl
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then
    printf '%s\n' 'Expected exactly one Verantyx wheel.' >&2
    exit 1
fi
printf '%s\n' 'Installing into this bundle only. pip may download declared dependencies. No model is called.'
.venv/bin/python -m pip install --disable-pip-version-check --no-input "$1"
printf '%s\n' 'Installed. Read README.ja.md, then run ./verantyx --help.'
