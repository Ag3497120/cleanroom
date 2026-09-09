#!/bin/zsh
set -eu
cd -- "${0:A:h}"
if [[ ! -f .gateway/config.json ]]; then
  /usr/local/bin/python3 scripts/configure-gateway.py
fi
if [[ ! -x .venv/bin/python ]]; then
  /usr/local/bin/python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python compute_gateway.py --config .gateway/config.json
