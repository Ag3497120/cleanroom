#!/bin/bash
# Explicit allowlist: never copy a project ledger, model adapter, auth or memory.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ $# != 1 ]]; then
  printf '%s\n' 'Usage: bash scripts/package-cli-preview.sh NEW_OUTPUT_DIRECTORY' >&2
  exit 2
fi
PYTHON=${VERANTYX_BUILD_PYTHON:-$ROOT/.venv/bin/python}
if [[ $(uname -s) != Darwin || $(uname -m) != arm64 ]]; then
  printf '%s\n' 'Build this binary preview on macOS arm64.' >&2
  exit 1
fi
OUT=$1
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
cd "$ROOT"
VERSION=$("$PYTHON" -c 'import sys,tomllib; print(tomllib.load(sys.stdin.buffer)["project"]["version"])' < core/pyproject.toml)
PIN=$("$PYTHON" -c 'import sys,json; print(json.load(sys.stdin)["runtime_sha256"])' < core/src/verantyx/cross-build.json)
ACTUAL=$(/usr/bin/shasum -a 256 cross/build/cross | awk '{print $1}')
if [[ "$PIN" != "$ACTUAL" ]]; then
  printf '%s\n' 'Cross binary does not match the registered build. Nothing will be published.' >&2
  exit 1
fi
NAME="verantyx-${VERSION}-macos-arm64"
STAGE="$OUT/$NAME"
mkdir -p "$STAGE/wheelhouse" "$STAGE/bin"
"$PYTHON" -m pip wheel --disable-pip-version-check --no-deps --no-build-isolation ./core --wheel-dir "$STAGE/wheelhouse"
cp cross/build/cross "$STAGE/bin/cross"
cp release/cli/install.command release/cli/verantyx release/cli/README.ja.md "$STAGE/"
chmod 755 "$STAGE/install.command" "$STAGE/verantyx" "$STAGE/bin/cross"
SOURCE=(core/src/verantyx core/pyproject.toml core/docs/QUICKSTART.ja.md
        core/tests/test_codex_wire.py core/tests/test_codex_plan_case_slots.py
        cross/src cross/tests cross/examples cross/CMakeLists.txt
        scripts/pin-cross-runtime.py scripts/package-cli-preview.sh release/cli)
if [[ -f LICENSE ]]; then
  cp LICENSE "$STAGE/LICENSE"
  SOURCE+=(LICENSE)
fi
COPYFILE_DISABLE=1 tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
  -czf "$STAGE/source.tar.gz" "${SOURCE[@]}"
printf 'version=%s\nplatform=macos-arm64\ncross_sha256=%s\nnotarized=false\n' "$VERSION" "$PIN" > "$STAGE/BUILD.txt"
/usr/bin/otool -l cross/build/cross | awk '/LC_BUILD_VERSION/{show=1} show && /minos/{print "minimum_macos=" $2; exit}' >> "$STAGE/BUILD.txt"
(
  cd "$STAGE"
  CONTENT=(README.ja.md BUILD.txt install.command verantyx bin/cross source.tar.gz wheelhouse/*.whl)
  if [[ -f LICENSE ]]; then CONTENT+=(LICENSE); fi
  /usr/bin/shasum -a 256 "${CONTENT[@]}" > checksums.sha256
)
COPYFILE_DISABLE=1 tar -czf "$OUT/$NAME.tar.gz" -C "$OUT" "$NAME"
(
  cd "$OUT"
  /usr/bin/shasum -a 256 "$NAME.tar.gz" > SHA256SUMS.txt
)
printf 'Prepared locally, not published:\n%s\n' "$OUT/$NAME.tar.gz"
