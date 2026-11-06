#!/usr/bin/env bash
# In-repo replacement for preview.sh. Builds a candidate and exits.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$HERE/safe_preview.py" "$@"
