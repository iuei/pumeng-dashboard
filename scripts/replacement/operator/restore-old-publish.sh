#!/usr/bin/env bash
set -euo pipefail
ROOT="${PUMENG_ROOT:-/workspace/music-biz/dashboard}"
src="$ROOT/publish.sh.disabled-20261106"
dst="$ROOT/publish.sh"
if [ ! -f "$src" ]; then
  echo "old_publish_backup=missing path=$src"
  exit 1
fi
mv -n "$src" "$dst"
echo "old_publish=restored path=$dst"
