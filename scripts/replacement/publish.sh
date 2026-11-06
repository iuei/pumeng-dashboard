#!/usr/bin/env bash
# In-repo replacement for the historical publish entry.
# It does not call gh, git, or the Contents API. The script on the old
# machine is not modified by installing this file.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/safe_publish.py" "$@"
