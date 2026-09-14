#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
if [ ! -x .venv/bin/python ]; then
    PYTHON_BIN=${VERANTYX_PYTHON:-}
    if [ -z "$PYTHON_BIN" ]; then
        for candidate in python3.13 python3.12 python3.11 python3; do
            if command -v "$candidate" >/dev/null 2>&1; then
                PYTHON_BIN=$(command -v "$candidate")
                break
            fi
        done
    fi
    if [ -z "$PYTHON_BIN" ]; then
        printf '%s\n' 'Python 3.11 or newer is required. Set VERANTYX_PYTHON.' >&2
        exit 1
    fi
    "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt -e ./core
npm ci --no-audit --no-fund
printf '%s\n' 'Development dependencies installed. No tests or model requests were run.'
