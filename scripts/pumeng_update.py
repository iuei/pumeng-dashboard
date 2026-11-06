"""Semantic snapshot check.

No network, no git, no production publish. The success baseline advances
only after a simulated publish with an approval bound to that candidate.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

# Top-level keys only. Nested fields with the same name stay substantive,
# so a task-level timestamp cannot hide inside this set.
SEMANTIC_IGNORE_KEYS = frozenset(
    {
        "updated_at",
        "source_updated_at",
        "generated_at",
        "build_time",
        "built_at",
        "fetched_at",
        "checked_at",
        "snapshot_written_at",
        "refresh_seconds",
    }
)

BEIJING_HOURS = frozenset({9, 12, 15, 18, 21})
SLOT_TOLERANCE_MINUTES = 15
LARGE_ID_DELTA = 3
LARGE_FIELD_CHANGES = 8

EXIT = {
    "no_semantic_change": 0,
    "candidate_ready": 0,
    "outside_slot": 0,
    "seeded": 0,
    "baseline_exists": 0,
    "simulated": 0,
    "missing_candidate": 2,
    "invalid_candidate": 3,
    "invalid_baseline": 3,
    "invalid_approval": 3,
    "invalid_state": 3,
    "invalid_now": 2,
    "mixed_invocation": 2,
    "bad_trigger": 2,
    "missing_approval": 4,
    "stale_approval": 4,
    "large_change_unconfirmed": 4,
    "bypass_rejected": 5,
    "production_publish_disabled": 5,
}


class SnapshotLoadError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sha256_json(obj) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_snapshot(obj: dict) -> dict:
    if not isinstance(obj, dict):
        raise SnapshotLoadError("snapshot_root_not_object")
    return {k: v for k, v in obj.items() if k not in SEMANTIC_IGNORE_KEYS}


def is_beijing_slot(now: datetime) -> bool:
    """True within 15 minutes of Beijing 09:00, 12:00, 15:00, 18:00 or 21:00.

    This classifies a scheduled read. It does not authorize publishing.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now_must_be_aware")
    local = now.astimezone(SHANGHAI)
    for hour in BEIJING_HOURS:
        center = local.replace(hour=hour, minute=0, second=0, microsecond=0)
        delta = abs(local - center)
        if delta.total_seconds() <= SLOT_TOLERANCE_MINUTES * 60:
            return True
    return False


def _identity_key(items):
    if not items:
        return None
    if all(isinstance(x, dict) and "id" in x for x in items):
        return "id"
    if all(isinstance(x, dict) and "date" in x for x in items):
        return "date"
    return None


def _keyed(a, b):
    if not isinstance(a, list) or not isinstance(b, list):
        return None
    ka = _identity_key(a)
    kb = _identity_key(b)
    if ka and kb and ka == kb:
        return ka
    if ka and len(b) == 0:
        return ka
    if kb and len(a) == 0:
        return kb
    if len(a) == 0 and len(b) == 0:
        return "id"
    return None


def _mark_tree(value, prefix, bucket, field_changes):
    field_changes.append(prefix)
    if isinstance(value, list):
        key = _identity_key(value)
        if key:
            for item in value:
                ident = item[key]
                bucket.append(f"{prefix}:{ident}")
                field_changes.append(f"{prefix}[{key}={ident}]")
    elif isinstance(value, dict):
        key = "id" if "id" in value else "date" if "date" in value else None
        if key:
            bucket.append(f"{prefix}:{value[key]}")


def _diff_keyed(a, b, prefix, key, field_changes, order_changes, added, removed):
    am = {}
    bm = {}
    dup = False
    for item in a:
        ident = item[key]
        if ident in am:
            dup = True
        am[ident] = item
    for item in b:
        ident = item[key]
        if ident in bm:
            dup = True
        bm[ident] = item
    if dup:
        field_changes.append(f"{prefix}.duplicate_ids")
    a_ids = [item[key] for item in a]
    b_ids = [item[key] for item in b]
    if not dup and a_ids != b_ids and set(map(str, a_ids)) == set(map(str, b_ids)):
        order_changes.append(prefix)
    for ident in sorted(set(am) | set(bm), key=lambda x: str(x)):
        path = f"{prefix}[{key}={ident}]"
        if ident not in am:
            added.append(f"{prefix}:{ident}")
            field_changes.append(path)
        elif ident not in bm:
            removed.append(f"{prefix}:{ident}")
            field_changes.append(path)
        else:
            _diff(am[ident], bm[ident], path, field_changes, order_changes, added, removed)


def _diff(a, b, prefix, field_changes, order_changes, added, removed):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if prefix == "" and k in SEMANTIC_IGNORE_KEYS:
                continue
            path = f"{prefix}.{k}" if prefix else k
            if k not in a:
                _mark_tree(b[k], path, added, field_changes)
            elif k not in b:
                _mark_tree(a[k], path, removed, field_changes)
            else:
                _diff(a[k], b[k], path, field_changes, order_changes, added, removed)
        return
    key = _keyed(a, b) if isinstance(a, list) and isinstance(b, list) else None
    if key and (len(a) or len(b)):
        _diff_keyed(a, b, prefix, key, field_changes, order_changes, added, removed)
        return
    if a != b:
        field_changes.append(prefix or "$")


def ignored_changes(baseline: dict, candidate: dict) -> list:
    found = []
    for key in SEMANTIC_IGNORE_KEYS:
        if (key in baseline or key in candidate) and baseline.get(key) != candidate.get(key):
            found.append(key)
    return sorted(found)


def summarize_diff(baseline: dict, candidate: dict) -> dict:
    field_changes = []
    order_changes = []
    added = []
    removed = []
    _diff(baseline, candidate, "", field_changes, order_changes, added, removed)
    field_changes = sorted(set(field_changes))
    order_changes = sorted(set(order_changes))
    added_ids = sorted(set(map(str, added)))
    removed_ids = sorted(set(map(str, removed)))
    metrics_changed = any(p == "metrics" or p.startswith("metrics.") or p.startswith("metrics[") for p in field_changes)
    reasons = []
    if metrics_changed:
        reasons.append("metrics")
    if len(added_ids) + len(removed_ids) >= LARGE_ID_DELTA:
        reasons.append("identity")
    if len(field_changes) >= LARGE_FIELD_CHANGES:
        reasons.append("field_volume")
    reasons.sort()
    semantic_change = bool(field_changes or order_changes or added_ids or removed_ids)
    return {
        "added_ids": added_ids,
        "field_changes": field_changes,
        "ignore_keys": sorted(SEMANTIC_IGNORE_KEYS),
        "ignored_changes": ignored_changes(baseline, candidate),
        "large": bool(reasons),
        "large_reasons": reasons,
        "large_rules": {
            "field_changes_at_least": LARGE_FIELD_CHANGES,
            "identity_delta_at_least": LARGE_ID_DELTA,
            "metrics_any_change": True,
        },
        "metrics_changed": metrics_changed,
        "order_changes": order_changes,
        "removed_ids": removed_ids,
        "semantic_change": semantic_change,
    }


def semantic_sha256(obj: dict) -> str:
    return sha256_json(canonical_snapshot(obj))


def validate_approval(approval, semantic_sha: str, summary_sha: str, large: bool):
    if not isinstance(approval, dict):
        return False, "missing_approval"
    required = ("candidate_semantic_sha256", "summary_sha256", "approver", "approved_at")
    if any(not isinstance(approval.get(k), str) or not approval.get(k).strip() for k in required):
        return False, "missing_approval"
    if approval["candidate_semantic_sha256"] != semantic_sha or approval["summary_sha256"] != summary_sha:
        return False, "stale_approval"
    if large and approval.get("large_change_confirmed") is not True:
        return False, "large_change_unconfirmed"
    return True, "ok"


def load_snapshot(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        raise SnapshotLoadError("unreadable") from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise SnapshotLoadError("JSONDecodeError") from None
    if not isinstance(data, dict):
        raise SnapshotLoadError("snapshot_root_not_object")
    return data


def _state_path(out_dir: Path) -> Path:
    return out_dir / "state" / "baseline.json"


def read_state(out_dir: Path):
    path = _state_path(out_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SnapshotLoadError("invalid_state") from None
    if not isinstance(data, dict) or not isinstance(data.get("semantic_sha256"), str):
        raise SnapshotLoadError("invalid_state")
    return data


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _result(status: str, **extra) -> dict:
    retryable = status in {
        "missing_candidate",
        "invalid_candidate",
        "invalid_baseline",
        "invalid_approval",
        "invalid_state",
        "invalid_now",
    }
    messages = {
        "no_semantic_change": "没有实质语义变化，不生成待发布候选。",
        "candidate_ready": "有实质变化，已写入待发布候选。未发布。",
        "outside_slot": "定时调用不在北京时间 9/12/15/18/21 点前后 15 分钟内，未生成待发布候选，也未模拟发布。",
        "seeded": "已把当前基线文件记为成功基线。未发布。",
        "baseline_exists": "成功基线已存在，种子命令没有覆盖它。",
        "simulated": "模拟发布已隔离写入输出目录。没有生产发布。",
        "missing_candidate": "没有候选快照，无法判断。可补上 --candidate 后重试。",
        "invalid_candidate": "候选快照读不出合法 JSON 对象。成功基线未推进。",
        "invalid_baseline": "基线快照读不出合法 JSON 对象。成功基线未推进。",
        "invalid_approval": "批准文件读不出合法 JSON 对象。成功基线未推进。",
        "invalid_state": "成功基线文件损坏，没有覆盖它。",
        "invalid_now": "现在时间必须带时区。",
        "mixed_invocation": "种子和检查不能写在同一次调用里。",
        "bad_trigger": "trigger 只能是 manual 或 scheduled。",
        "missing_approval": "模拟发布缺少绑定当前候选的批准。",
        "stale_approval": "批准的语义哈希或摘要哈希与当前候选不一致，不能复用。",
        "large_change_unconfirmed": "这次是大改，批准里必须有 large_change_confirmed=true，且仍绑定当前候选。",
        "bypass_rejected": "审批门不能跳过。定时和手动走同一条门。",
        "production_publish_disabled": "生产发布在这个入口里没有实现，环境变量也不能打开它。",
    }
    body = {
        "baseline_advanced": False,
        "exit_code": EXIT[status],
        "message": messages[status],
        "production_publish": False,
        "retryable": retryable,
        "status": status,
    }
    body.update(extra)
    return body


def _persist(out_dir: Path, result: dict, *, failure: bool) -> None:
    stamp = datetime.now(SHANGHAI).strftime("%Y%m%dT%H%M%S%f")
    _write_json(out_dir / "status.json", result)
    _write_json(out_dir / "logs" / f"{stamp}-{result['status']}.json", result)
    if failure:
        _write_json(out_dir / "retry" / "last_failure.json", result)


def execute(
    *,
    baseline_path: Path,
    candidate_path: Path | None,
    trigger: str,
    now: datetime,
    now_source: str,
    approval: dict | None,
    approval_error: str | None,
    simulate: bool,
    publish: bool,
    bypass: bool,
    seed: bool,
    out_dir: Path,
    now_error: bool = False,
) -> dict:
    """Run one check. Never pushes, never calls the network."""
    out_dir = Path(out_dir)
    if now_error:
        result = _result("invalid_now", now_source=now_source, trigger=trigger, production_publish=False)
        _persist(out_dir, result, failure=True)
        return result
    state_before = None
    try:
        state_before = read_state(out_dir)
    except SnapshotLoadError:
        result = _result("invalid_state", now=_iso(now), now_source=now_source, trigger=trigger)
        _persist(out_dir, result, failure=True)
        return result

    before_sha = None if state_before is None else state_before.get("semantic_sha256")

    def finish(status: str, *, failure: bool, advanced: bool = False, **extra):
        result = _result(status, baseline_advanced=advanced, **extra)
        result["baseline_sha_before"] = before_sha
        result["baseline_sha_after"] = before_sha if not advanced else extra.get("candidate_semantic_sha256", before_sha)
        if advanced:
            result["baseline_sha_after"] = extra.get("candidate_semantic_sha256")
        _persist(out_dir, result, failure=failure)
        return result

    common = {"now": _iso(now), "now_source": now_source, "trigger": trigger}

    if bypass:
        return finish("bypass_rejected", failure=True, **common)
    if publish:
        return finish(
            "production_publish_disabled",
            failure=True,
            allow_env_ignored=True,
            **common,
        )
    if seed and (candidate_path or simulate or approval):
        return finish("mixed_invocation", failure=True, **common)
    if trigger not in {"manual", "scheduled"}:
        return finish("bad_trigger", failure=True, **common)

    try:
        baseline = load_snapshot(Path(baseline_path))
    except SnapshotLoadError as exc:
        code = "invalid_baseline" if exc.code in {"JSONDecodeError", "snapshot_root_not_object", "unreadable"} else "invalid_baseline"
        return finish(code, failure=True, error_type=exc.code, **common)

    base_sha = semantic_sha256(baseline)
    if seed:
        if state_before is not None:
            return finish("baseline_exists", failure=False, semantic_sha256=before_sha, **common)
        _write_json(
            _state_path(out_dir),
            {"advanced_at": _iso(now), "semantic_sha256": base_sha, "source": "seed"},
        )
        return finish(
            "seeded",
            failure=False,
            advanced=True,
            candidate_semantic_sha256=base_sha,
            semantic_sha256=base_sha,
            **common,
        )

    if candidate_path is None:
        return finish("missing_candidate", failure=True, semantic_sha256=base_sha, **common)

    try:
        candidate = load_snapshot(Path(candidate_path))
    except SnapshotLoadError as exc:
        return finish("invalid_candidate", failure=True, error_type=exc.code, semantic_sha256=base_sha, **common)

    summary = summarize_diff(baseline, candidate)
    cand_sha = semantic_sha256(candidate)
    summary_sha = sha256_json(summary)
    in_slot = is_beijing_slot(now)
    diff_info = {
        "candidate_semantic_sha256": cand_sha,
        "comparison_semantic_sha256": base_sha,
        "field_change_count": len(summary["field_changes"]),
        "in_beijing_slot": in_slot,
        "large": summary["large"],
        "large_reasons": summary["large_reasons"],
        "semantic_sha256": cand_sha,
        "summary_sha256": summary_sha,
        **common,
    }

    if trigger == "scheduled" and not in_slot:
        return finish("outside_slot", failure=False, would_change=summary["semantic_change"], **diff_info)

    if not summary["semantic_change"]:
        return finish("no_semantic_change", failure=False, ignored_changes=summary["ignored_changes"], **diff_info)

    cand_dir = out_dir / "candidates" / cand_sha
    _write_json(cand_dir / "snapshot.json", candidate)
    _write_json(cand_dir / "summary.json", summary)
    _write_json(
        cand_dir / "manifest.json",
        {
            "candidate_semantic_sha256": cand_sha,
            "large": summary["large"],
            "status": "candidate_ready",
            "summary_sha256": summary_sha,
            "trigger": trigger,
        },
    )

    if not simulate:
        return finish("candidate_ready", failure=False, **diff_info)

    if approval_error:
        return finish("invalid_approval", failure=True, error_type=approval_error, **diff_info)
    ok, reason = validate_approval(approval, cand_sha, summary_sha, summary["large"])
    if not ok:
        return finish(reason, failure=True, **diff_info)

    if state_before and state_before.get("semantic_sha256") == cand_sha:
        return finish("simulated", failure=False, approver=approval["approver"], already_current=True, **diff_info)

    sim = out_dir / "simulated" / cand_sha
    _write_json(sim / "snapshot.json", candidate)
    _write_json(
        sim / "receipt.json",
        {
            "approver": approval["approver"],
            "candidate_semantic_sha256": cand_sha,
            "isolated": True,
            "mode": "simulated",
            "production": False,
            "summary_sha256": summary_sha,
            "trigger": trigger,
        },
    )
    _write_json(
        _state_path(out_dir),
        {
            "advanced_at": _iso(now),
            "approver": approval["approver"],
            "semantic_sha256": cand_sha,
            "source": "simulate",
            "summary_sha256": summary_sha,
        },
    )
    return finish("simulated", failure=False, advanced=True, approver=approval["approver"], **diff_info)


def _iso(now: datetime) -> str:
    if now.tzinfo is None:
        return now.isoformat()
    return now.astimezone(SHANGHAI).isoformat()


def production_publish_implemented() -> bool:
    """Structural guarantee: this module has no publisher to turn on."""
    return False


def env_requests_bypass() -> bool:
    return "PUMENG_SKIP_APPROVAL" in os.environ
