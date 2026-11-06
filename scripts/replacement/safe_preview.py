#!/usr/bin/env python3
"""Replacement for preview.sh. Builds a candidate and exits. It does not publish or serve."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_update import parse_now  # noqa: E402
from replacement.build_snapshot import SchemaError, SensitiveMaterial, build_snapshot  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="只构建候选，不发布，不启动服务。")
    parser.add_argument("--tasks", required=True)
    parser.add_argument("--now", default=None)
    parser.add_argument("--out", default=".pumeng-update-out")
    parser.add_argument("--serve", action="store_true", help="替换包不提供服务器。")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if args.serve:
        body = {"exit_code": 5, "production_publish": False, "status": "serve_not_in_replacement"}
        print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
        return 5
    now, _source, now_error = parse_now(args.now)
    if now_error:
        print(json.dumps({"exit_code": 2, "status": "invalid_now"}, ensure_ascii=False))
        return 2
    try:
        tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
        built = build_snapshot(tasks, now)
    except (OSError, json.JSONDecodeError, SchemaError, SensitiveMaterial) as exc:
        print(json.dumps({"exit_code": 3, "error_type": type(exc).__name__, "status": "preview_failed"}, ensure_ascii=False))
        return 3
    built.pop("_scan", None)
    out.mkdir(parents=True, exist_ok=True)
    target = out / "preview-candidate.json"
    target.write_text(json.dumps(built, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"exit_code": 0, "path": str(target), "production_publish": False, "status": "preview_built"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
