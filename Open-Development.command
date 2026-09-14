#!/bin/zsh
set -eu
cd -- "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export VERANTYX_HOME="$PWD/core"
export VERANTYX_PRECEDENT="$PWD/execution"
export VERANTYX_CROSS="$PWD/cross/build/cross"
if [[ ! -x .venv/bin/python || ! -d node_modules ]]; then
  /bin/sh scripts/bootstrap-development.sh
fi
case "${1:-cli}" in
  web|--web)
    # Local frontend development only; no public tunnel or credentials are used.
    exec npm run dev -- --host 127.0.0.1 --port "${VERANTYX_DEV_PORT:-4175}"
    ;;
  cli|--cli)
    target="${VERANTYX_PROJECT:-$PWD/.local-development/project}"
    mkdir -p -- "$target"
    if [[ ! -f "$target/.verantyx/config.json" ]]; then
      .venv/bin/python core/bin/verantyx --project "$target" --lang "${VERANTYX_LANG:-ja}" \
        setup --non-interactive --name 'Local development' --purpose 'Resume Verantyx development' \
        --learning manual --max-items 1
    fi
    exec .venv/bin/python core/bin/verantyx --project "$target" --lang "${VERANTYX_LANG:-ja}" start
    ;;
  *)
    print -u2 'Usage: Open-Development.command [cli|web]'
    exit 2
    ;;
esac
