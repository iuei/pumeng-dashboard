#!/usr/bin/env python3
"""Standard entry for the external Beijing-time checker and for a manual run.

Default trigger is scheduled. Default mode is dry-run: a semantic change writes
a candidate under --out and does not publish. --publish always refuses.
--simulate writes only inside --out after an approval bound to this candidate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from publish_paths import list_paths
from pumeng_update import SHANGHAI, env_requests_bypass, execute


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查快照语义差异。默认干跑，不能生产发布。")
    parser.add_argument("--baseline", default="data.json", help="已发布快照路径")
    parser.add_argument("--candidate", default=None, help="待比较的新快照路径")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="scheduled")
    parser.add_argument("--now", default=None, help="测试用带时区时间，不能代替批准")
    parser.add_argument("--approval", default=None, help="绑定当前候选哈希的批准 JSON")
    parser.add_argument("--simulate", action="store_true", help="隔离模拟发布，仍要批准")
    parser.add_argument("--publish", action="store_true", help="始终拒绝")
    parser.add_argument("--bypass-approval", action="store_true", help="始终拒绝")
    parser.add_argument("--seed-baseline", action="store_true", help="仅在没有成功基线时登记当前文件")
    parser.add_argument("--list-paths", action="store_true", help="打印发布路径分类，不发布")
    parser.add_argument("--out", default=".pumeng-update-out")
    return parser


def parse_now(text: str | None):
    if text is None:
        return datetime.now(SHANGHAI), "clock", False
    raw = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(SHANGHAI), "injected", True
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return datetime.now(SHANGHAI), "injected", True
    return parsed, "injected", False


def load_approval(path: str | None):
    if path is None:
        return None, None
    file = Path(path)
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except OSError:
        return None, "unreadable"
    except json.JSONDecodeError:
        return None, "JSONDecodeError"
    if not isinstance(data, dict):
        return None, "approval_root_not_object"
    return data, None


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    bypass = bool(args.bypass_approval or env_requests_bypass())
    if args.list_paths and not args.publish and not bypass and not args.simulate:
        json.dump({"paths": list_paths(), "production_control_configured": False}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    now, now_source, now_error = parse_now(args.now)
    approval, approval_error = (None, None)
    if not now_error:
        approval, approval_error = load_approval(args.approval)
    result = execute(
        baseline_path=Path(args.baseline),
        candidate_path=Path(args.candidate) if args.candidate else None,
        trigger=args.trigger,
        now=now,
        now_source=now_source,
        approval=approval,
        approval_error=approval_error,
        simulate=args.simulate,
        publish=args.publish,
        bypass=bypass,
        seed=bool(args.seed_baseline),
        out_dir=Path(args.out),
        now_error=now_error,
    )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return int(result["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
