#!/usr/bin/env bash
# Reversible rename of the on-site publish.sh. Does not edit routine or build_data.py.
set -euo pipefail
ROOT="${PUMENG_ROOT:-/workspace/music-biz/dashboard}"
src="$ROOT/publish.sh"
dst="$ROOT/publish.sh.disabled-20261106"
if [ -f "$dst" ] && [ ! -f "$src" ]; then
  echo "old_publish=already_disabled dest=$dst"
  exit 0
fi
if [ ! -f "$src" ]; then
  echo "old_publish=missing path=$src"
  exit 1
fi
mv -n "$src" "$dst"
echo "old_publish=renamed dest=$dst"
