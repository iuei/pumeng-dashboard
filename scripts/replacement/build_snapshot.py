"""Build a public snapshot from a tasks object.

The historical detector literals for account and id fragments were redacted
before this copy existed. Those placeholders are not rules. This scanner uses
generic patterns and fails closed when one matches. It does not claim to
reproduce the original account or id rules; a real tasks file still needs a
local test against the untouched source script.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

LINE_LABELS = {"pumeng": "谱梦", "douyin": "抖音"}
HISTORICAL_DETECTORS_AVAILABLE = False
PLACEHOLDER_MARKERS = ("[REDACTED_ACCOUNT_PATTERN]", "[REDACTED_ID_PATTERN]")

_RULES = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{16,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{8,}", re.I)),
    ("sk_token", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("secret_assignment", re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\b\s*[=:]\s*\S+")),
    ("gh_auth_token_command", re.compile(r"gh\s+auth\s+token")),
    ("opaque_hex", re.compile(r"\b[A-Fa-f0-9]{40,}\b")),
)


class SensitiveMaterial(Exception):
    def __init__(self, rule_ids):
        self.rule_ids = tuple(sorted(set(rule_ids)))
        super().__init__("sensitive_material")


class SchemaError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def scan_text(text: str) -> list:
    if not text:
        return []
    return [rule_id for rule_id, pattern in _RULES if pattern.search(text)]


def placeholders_in(text: str) -> list:
    return [marker for marker in PLACEHOLDER_MARKERS if marker in text]


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def scan_tasks(tasks: dict) -> dict:
    hits = []
    placeholders = []
    for text in _strings(tasks):
        hits.extend(scan_text(text))
        placeholders.extend(placeholders_in(text))
    return {
        "historical_detectors_available": HISTORICAL_DETECTORS_AVAILABLE,
        "placeholder_markers_are_not_rules": True,
        "placeholders_seen": sorted(set(placeholders)),
        "rule_ids": sorted(set(hits)),
    }


def _task(item: dict) -> dict:
    out = {
        "id": item.get("id"),
        "owner": item.get("owner"),
        "title": item.get("title"),
        "line": item.get("line"),
    }
    for key in ("note", "eta", "blocker"):
        value = item.get(key)
        if value:
            out[key] = value
    return out


def _bucket(items) -> list:
    if items is None:
        return []
    if not isinstance(items, list):
        raise SchemaError("bucket_not_list")
    out = []
    for item in items:
        if not isinstance(item, dict):
            raise SchemaError("task_not_object")
        out.append(_task(item))
    return out


def build_snapshot(tasks: dict, now: datetime) -> dict:
    if not isinstance(tasks, dict):
        raise SchemaError("tasks_root_not_object")
    report = scan_tasks(tasks)
    if report["rule_ids"]:
        raise SensitiveMaterial(report["rule_ids"])
    lines_in = tasks.get("lines") or {}
    if lines_in and not isinstance(lines_in, dict):
        raise SchemaError("lines_not_object")
    lines = {}
    for key in LINE_LABELS:
        bucket = lines_in.get(key) or {}
        if bucket and not isinstance(bucket, dict):
            raise SchemaError("line_not_object")
        lines[key] = {
            "doing": _bucket(bucket.get("doing")),
            "todo": _bucket(bucket.get("todo")),
            "paused": _bucket(bucket.get("paused")),
            "done_today": _bucket(bucket.get("done_today")),
        }
    decisions = []
    for item in tasks.get("decisions") or []:
        if not isinstance(item, dict):
            raise SchemaError("decision_not_object")
        decisions.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "note": item.get("note"),
                "owner": item.get("owner"),
            }
        )
    timeline = []
    for day in tasks.get("timeline") or []:
        if not isinstance(day, dict):
            raise SchemaError("timeline_day_not_object")
        timeline.append(
            {
                "date": day.get("date"),
                "did": [str(x) for x in (day.get("did") or [])],
                "closed": [str(x) for x in (day.get("closed") or [])],
                "opened": [str(x) for x in (day.get("opened") or [])],
            }
        )
    metrics = tasks.get("metrics") or {}
    if metrics and not isinstance(metrics, dict):
        raise SchemaError("metrics_not_object")
    pm_ids = metrics.get("pm_ids")
    if pm_ids is None:
        pm_count = 0
    elif isinstance(pm_ids, list):
        pm_count = len(pm_ids)
    else:
        raise SchemaError("pm_ids_not_list")
    today = {"doing": [], "done_today": [], "todo": [], "paused": []}
    for key, label in LINE_LABELS.items():
        for name in today:
            for item in lines[key][name]:
                today[name].append({**item, "line_label": label})
    if now.tzinfo is None or now.utcoffset() is None:
        raise SchemaError("now_must_be_aware")
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    stamp = local.strftime("%Y-%m-%d %H:%M Asia/Shanghai")
    built = {
        "title": "谱梦 · 进度监控",
        "updated_at": stamp,
        "source_updated_at": tasks.get("updated_at"),
        "refresh_seconds": 30,
        "today": today,
        "lines": lines,
        "decisions": decisions,
        "timeline": timeline,
        "metrics": {
            "songs_on_platform_approx": metrics.get("songs_on_platform_approx"),
            "feishu_base": metrics.get("feishu_base"),
            "feishu_tables": metrics.get("feishu_tables"),
            "pm_ids_count": pm_count,
        },
        "disclaimer": "本页仅含进度与聚合数字，不含单曲收益明细、账号、密钥或飞书原文。",
    }
    encoded = json.dumps(built, ensure_ascii=False)
    leaked = scan_text(encoded)
    if leaked:
        raise SensitiveMaterial(leaked)
    if '"pm_ids"' in encoded:
        raise SchemaError("pm_ids_leaked")
    built["_scan"] = report
    return built
