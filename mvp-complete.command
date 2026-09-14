#!/bin/zsh
set -eu
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$PWD/core/src"
export VERANTYX_CROSS="$PWD/cross/build/cross"
export VERANTYX_PRECEDENT="$PWD/execution"
project="${VERANTYX_MVP_PROJECT:-$PWD/../mvp-complete-20260911-5GK0zW}"
exec "$PWD/.venv/bin/python" -m verantyx --project "$project" --lang ja develop
