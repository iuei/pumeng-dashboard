#!/usr/bin/env bash
# Isolated test runner. Does not publish, schedule, or touch GitHub.
# Copies each raw log to artifacts/ and, when present, /opt/cursor/artifacts/.
# Also writes a SHA-named copy so a later run cannot be mistaken for this one.
set -euo pipefail
cd "$(dirname "$0")/.."
SHORT="$(git rev-parse --short=12 HEAD)"
mkdir -p artifacts
OPT="/opt/cursor/artifacts"
mkdir -p "$OPT" 2>/dev/null || true

publish() {
  local src="$1" stem="$2"
  cp -f "$src" "artifacts/${stem}-${SHORT}.log"
  cp -f "$src" "artifacts/${stem}-replacement-final.log"
  if [[ -d "$OPT" ]]; then
    cp -f "$src" "$OPT/${stem}.log"
    cp -f "$src" "$OPT/${stem}-${SHORT}.log"
    cp -f "$src" "$OPT/${stem}-replacement-final.log"
  fi
}

python3 -m unittest discover -s tests -v 2>&1 | tee artifacts/test-python.log
publish artifacts/test-python.log test-python
node --test tests/test_dashboard.js 2>&1 | tee artifacts/test-node.log
publish artifacts/test-node.log test-node
if [[ ! -d .test-tools/node_modules/playwright-core ]]; then
  npm install --prefix .test-tools playwright-core --silent
fi
NODE_PATH=".test-tools/node_modules${NODE_PATH:+:$NODE_PATH}" node tests/browser_check.cjs 2>&1 | tee artifacts/test-browser.log
publish artifacts/test-browser.log test-browser
