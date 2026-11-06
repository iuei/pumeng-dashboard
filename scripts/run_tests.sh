#!/usr/bin/env bash
# Isolated test runner. Does not publish, schedule, or touch GitHub.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
python3 -m unittest discover -s tests -v > artifacts/test-python.log 2>&1
node --test tests/test_dashboard.js > artifacts/test-node.log 2>&1
if [[ ! -d .test-tools/node_modules/playwright-core ]]; then
  npm install --prefix .test-tools playwright-core --silent
fi
NODE_PATH=".test-tools/node_modules${NODE_PATH:+:$NODE_PATH}" node tests/browser_check.cjs > artifacts/test-browser.log 2>&1
cat artifacts/test-python.log artifacts/test-node.log artifacts/test-browser.log
