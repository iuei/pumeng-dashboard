#!/usr/bin/env python3
"""Replacement for the historical publish entry.

Builds a candidate from a tasks file, then uses the same check as
scripts/check_update.py. It does not read gh tokens, does not spawn git,
and does not call the Contents API. Production flags are refused.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_update import load_approval, parse_now  # noqa: E402
from pumeng_update import SnapshotLoadError, env_requests_bypass, execute, load_snapshot  # noqa: E402
from replacement.build_snapshot import SchemaError, SensitiveMaterial, build_snapshot  # noqa: E402
from replacement.production_adapter import (  # noqa: E402
    load_materials,
    run_controlled_publish,
    select_publisher,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="隔离替换历史 publish。默认干跑，不能生产发布。")
    parser.add_argument("--tasks", default=None, help="tasks.json 路径。不传则不会去读历史目录。")
    parser.add_argument("--baseline", default="data.json")
    parser.add_argument("--trigger", choices=["manual", "scheduled"], default="scheduled")
    parser.add_argument("--now", default=None)
    parser.add_argument("--approval", default=None)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--publish", action="store_true", help="始终拒绝")
    parser.add_argument("--push", action="store_true", help="始终拒绝")
    parser.add_argument("--contents-api", action="store_true", help="始终拒绝")
    parser.add_argument("--bypass-approval", action="store_true", help="始终拒绝")
    parser.add_argument("--production", action="store_true", help="受控发布。需要安装配置和外部放行材料。")
    parser.add_argument("--detect", action="store_true", help="只判断能否发布，不调用发布器。")
    parser.add_argument("--install", default=None)
    parser.add_argument("--release", default=None)
    parser.add_argument("--running-sha", default=None)
    parser.add_argument("--out", default=".pumeng-update-out")
    return parser


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _failure(out: Path, status: str, code: int, **extra) -> dict:
    body = {
        "baseline_advanced": False,
        "called_network": False,
        "exit_code": code,
        "production_publish": False,
        "read_gh_token": False,
        "status": status,
        **extra,
    }
    _write(out / "status.json", body)
    _write(out / "retry" / "last_failure.json", body)
    return body


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    now, now_source, now_error = parse_now(args.now)
    bypass = bool(args.bypass_approval or env_requests_bypass())
    legacy_force = bool(args.publish or args.push or args.contents_api)
    if args.production and legacy_force:
        body = _failure(out, "legacy_flag_cannot_bypass", 5, message="旧的 publish/push/contents-api 开关不能进入受控发布。")
        print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
        return 5
    production_request = legacy_force
    if now_error or bypass or production_request:
        result = execute(
            baseline_path=Path(args.baseline),
            candidate_path=None,
            trigger=args.trigger,
            now=now,
            now_source=now_source,
            approval=None,
            approval_error=None,
            simulate=False,
            publish=production_request,
            bypass=bypass,
            seed=False,
            out_dir=out,
            now_error=now_error,
        )
        result["called_network"] = False
        result["read_gh_token"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return int(result["exit_code"])
    if not args.tasks:
        body = _failure(out, "missing_tasks", 2, message="没有 --tasks。替换入口不会自己打开历史 tasks.json。")
        print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    try:
        tasks = json.loads(Path(args.tasks).read_text(encoding="utf-8"))
    except OSError:
        body = _failure(out, "invalid_tasks", 3, error_type="unreadable")
        print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
        return 3
    except json.JSONDecodeError:
        body = _failure(out, "invalid_tasks", 3, error_type="JSONDecodeError")
        print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
        return 3
    try:
        built = build_snapshot(tasks, now)
    except SensitiveMaterial as exc:
        body = _failure(
            out,
            "sensitive_rejected",
            3,
            error_type="SensitiveMaterial",
            historical_detectors_available=False,
            rule_ids=list(exc.rule_ids),
            message="候选含敏感形态，已拒绝写出。日志只有规则名。原始账号/标识正则不在本包，需用真实源在本地再测。",
        )
        print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
        return 3
    except SchemaError as exc:
        body = _failure(out, "invalid_tasks", 3, error_type=exc.code)
        print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
        return 3
    scan = built.pop("_scan")
    candidate = out / "built-candidate.json"
    _write(candidate, built)
    if args.production or args.detect:
        try:
            baseline = load_snapshot(Path(args.baseline))
        except SnapshotLoadError as exc:
            body = _failure(out, "invalid_baseline", 3, error_type=exc.code)
            print(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True))
            return 3
        install, _install_error, release, _release_error = load_materials(args.install, args.release)
        result = run_controlled_publish(
            baseline=baseline,
            candidate=built,
            trigger=args.trigger,
            now=now,
            install=install,
            release=release,
            running_sha=args.running_sha or "",
            out_dir=out,
            publisher=select_publisher(install),
            detect_only=bool(args.detect),
            candidate_bytes=candidate.read_bytes(),
        )
        result["historical_detectors_available"] = scan["historical_detectors_available"]
        result["read_gh_token"] = False
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return int(result["exit_code"])
    approval, approval_error = load_approval(args.approval)
    result = execute(
        baseline_path=Path(args.baseline),
        candidate_path=candidate,
        trigger=args.trigger,
        now=now,
        now_source=now_source,
        approval=approval,
        approval_error=approval_error,
        simulate=bool(args.simulate),
        publish=False,
        bypass=False,
        seed=False,
        out_dir=out,
        now_error=False,
    )
    result["called_network"] = False
    result["historical_detectors_available"] = scan["historical_detectors_available"]
    result["read_gh_token"] = False
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
