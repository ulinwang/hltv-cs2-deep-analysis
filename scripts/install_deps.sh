#!/usr/bin/env bash
set -euo pipefail

# Check Python version (require 3.10+)
PYTHON_CMD="${PYTHON:-python3}"
if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "[error] python3 not found. Please install Python 3.10 or higher."
  exit 1
fi

PY_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ]]; then
  echo "[error] Python $PY_VERSION is too old. Require Python 3.10+."
  echo "[hint] Install Python 3.10+ or use a version manager like pyenv."
  exit 1
fi

echo "python_version=$PY_VERSION"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ_FILE="$SCRIPT_DIR/../requirements.txt"

if $PYTHON_CMD -m pip install --user -r "$REQ_FILE" >/dev/null 2>&1; then
  echo "python_deps_mode=user"
elif $PYTHON_CMD -m pip install --break-system-packages --user -r "$REQ_FILE"; then
  echo "python_deps_mode=break-system-packages+user"
elif $PYTHON_CMD -m pip install -r "$REQ_FILE"; then
  echo "python_deps_mode=system"
else
  echo "[error] failed to install python dependencies from $REQ_FILE"
  echo "[hint] try a virtualenv:"
  echo "       python3 -m venv .venv && source .venv/bin/activate && python3 -m pip install -r $REQ_FILE"
  exit 1
fi
echo "installed_python_reqs=$REQ_FILE"

missing=()
for cmd in node npm npx; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    missing+=("$cmd")
  fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "[error] missing node runtime tools: ${missing[*]}"
  echo "[hint] install Node.js (includes npm/npx), then rerun this script."
  exit 1
fi

if npx --yes --package @playwright/cli playwright-cli --help >/dev/null 2>&1; then
  echo "playwright_cli=ready"
else
  echo "[error] playwright-cli bootstrap failed."
  echo "[hint] check network access to npm registry, then run:"
  echo "       npx --yes --package @playwright/cli playwright-cli --help"
  exit 1
fi
