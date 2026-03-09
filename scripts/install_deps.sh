#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ_FILE="$SCRIPT_DIR/../requirements.txt"

if python3 -m pip install --user -r "$REQ_FILE" >/dev/null 2>&1; then
  echo "python_deps_mode=user"
elif python3 -m pip install --break-system-packages --user -r "$REQ_FILE"; then
  echo "python_deps_mode=break-system-packages+user"
elif python3 -m pip install -r "$REQ_FILE"; then
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
