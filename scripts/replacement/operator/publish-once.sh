#!/usr/bin/env bash
# One controlled publish through safe_publish.py. The pages work tree is PUMENG_ROOT/.pages-repo.
# Running-code identity stays release.approved_code_sha. It is not the moving pages HEAD.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${PUMENG_ROOT:-/workspace/music-biz/dashboard}"
INSTALL="${PUMENG_INSTALL:-$ROOT/pumeng-release/install.json}"
RELEASE="${PUMENG_RELEASE:-$ROOT/pumeng-release/release.json}"
OUT="${PUMENG_OUT:-$ROOT/pumeng-update-out/production}"
NOW="${PUMENG_PUBLISH_NOW:-}"

close_network() {
  if [ -f "$INSTALL" ]; then
    python3 -c 'import json,sys; p=sys.argv[1]; d=json.load(open(p,encoding="utf-8")); d["network_publisher"]=False; open(p,"w",encoding="utf-8").write(json.dumps(d,ensure_ascii=False,indent=2)+"\n")' "$INSTALL" || true
  fi
}
trap close_network EXIT

if [ "${PUMENG_CONFIRM_PUBLISH:-}" != "1" ] || [ -z "$NOW" ]; then
  echo "status=confirmation_missing"
  exit 2
fi
if [ ! -d "$ROOT/.pages-repo/.git" ]; then
  echo "bind_status=missing_work_tree"
  echo "work_tree=$ROOT/.pages-repo"
  exit 4
fi
PUMENG_RELEASE="$RELEASE" bash "$HERE/bind-check.sh" "$ROOT/.pages-repo"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8")); assert d.get("work_tree")==sys.argv[2]; remote=d.get("remote",""); assert "@" not in remote and "ghp_" not in remote' \
  "$INSTALL" "$ROOT/.pages-repo"
running="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["approved_code_sha"])' "$RELEASE")"
remote_value="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8")).get("remote",""))' "$INSTALL")"
if printf '%s' "$remote_value" | grep -q 'github.com' && [ "${PUMENG_ALLOW_GITHUB_PUBLISH:-}" != "1" ]; then
  echo "status=github_publish_not_allowed"
  exit 2
fi
python3 "$HERE/../safe_publish.py" \
  --tasks "$ROOT/tasks.json" \
  --baseline "$ROOT/.pages-repo/data.json" \
  --trigger manual \
  --now "$NOW" \
  --install "$INSTALL" \
  --release "$RELEASE" \
  --running-sha "$running" \
  --production \
  --out "$OUT"
