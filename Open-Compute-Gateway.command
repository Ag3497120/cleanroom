#!/bin/zsh
set -eu
cd -- "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x .venv/bin/python ]]; then
  python_bin="${VERANTYX_PYTHON:-}"
  if [[ -z "$python_bin" ]]; then
    for candidate in python3.13 python3.12 python3.11 python3; do
      if command -v "$candidate" >/dev/null 2>&1; then
        python_bin="$(command -v "$candidate")"
        break
      fi
    done
  fi
  if [[ -z "$python_bin" ]]; then
    print -u2 'Python 3.11 or newer is required. Set VERANTYX_PYTHON to its executable.'
    exit 1
  fi
  "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt -e ./core
if [[ ! -x cross/build/cross ]]; then
  cmake -S cross -B cross/build -DCMAKE_BUILD_TYPE=Release
  cmake --build cross/build -j 2
fi
if [[ ! -f core/src/verantyx/cross-build.json ]]; then
  .venv/bin/python scripts/pin-cross-runtime.py
fi
if [[ ! -f .gateway/config.json ]]; then
  .venv/bin/python scripts/configure-gateway.py
fi
exec .venv/bin/python compute_gateway.py --config .gateway/config.json
