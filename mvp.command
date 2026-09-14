#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LIBRARY="${VERANTYX_LIBRARY:-$ROOT/../mvp-session-20260911-tzFCUy}"
export VERANTYX_CROSS="${VERANTYX_CROSS:-$ROOT/cross/build/cross}"
printf '%s\n' 'Verantyx CLI MVP' 'Default library: recorded synthetic MVP examples, not certified personal mastery.'
exec "$ROOT/.venv/bin/python" -m verantyx --project "$LIBRARY" --lang ja skills --interactive
