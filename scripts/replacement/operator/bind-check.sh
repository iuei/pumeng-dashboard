#!/usr/bin/env bash
# Dynamic bind for a pages work tree. MERGE/TREE/DATA are not installation constants.
# The approved code identity comes from release.json. A later data.json-only descendant stays ready.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${PUMENG_ROOT:-/workspace/music-biz/dashboard}"
WORK="${1:-$ROOT/.pages-repo}"
RELEASE="${PUMENG_RELEASE:-$ROOT/pumeng-release/release.json}"
PY="$(cd "$HERE/../.." && pwd)"
if [ ! -f "$RELEASE" ]; then
  echo "bind_status=missing_release"
  exit 4
fi
export PUMENG_BIND_WORK="$WORK"
export PUMENG_BIND_RELEASE="$RELEASE"
export PYTHONPATH="$PY${PYTHONPATH:+:$PYTHONPATH}"
python3 - << 'PY'
import json, os, sys
sys.path.insert(0, os.environ["PYTHONPATH"].split(":")[0])
from replacement.production_adapter import evaluate_bind
release = json.loads(open(os.environ["PUMENG_BIND_RELEASE"], encoding="utf-8").read())
result = evaluate_bind(
    os.environ["PUMENG_BIND_WORK"],
    release.get("approved_code_sha"),
    release.get("named_code_sha"),
)
for key in ("head", "tree", "data_sha256", "bind_status", "approved_code_sha", "named_code_sha"):
    if key in result and result[key] is not None:
        print(f"{key}={result[key]}")
sys.exit(int(result["exit_code"]))
PY
status=$?
if [ "$status" -ne 0 ]; then
  exit "$status"
fi
if [ -d "$WORK/.git" ]; then
  export PUMENG_REMOTE_CHECK
  PUMENG_REMOTE_CHECK="$(git -C "$WORK" remote get-url origin 2>/dev/null || true)"
  python3 -c 'import os; r=os.environ.get("PUMENG_REMOTE_CHECK",""); rest=r.split("://",1)[-1] if "://" in r else r; bad=bool(r) and (("@" in rest) or ("ghp_" in r) or ("://" not in r)); print("remote_has_credential="+("yes" if bad else "no")); raise SystemExit(9 if bad else 0)'
fi
echo "bind_status=ready"
