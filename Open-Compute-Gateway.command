#!/bin/zsh
set -eu
cd -- "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  /usr/local/bin/python3 -m venv .venv
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
