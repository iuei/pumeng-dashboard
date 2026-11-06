import ast
import hashlib
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from pumeng_update import (  # noqa: E402
    BEIJING_HOURS,
    SLOT_TOLERANCE_MINUTES,
    SEMANTIC_IGNORE_KEYS,
    is_beijing_slot,
    semantic_sha256,
    sha256_json,
    summarize_diff,
)
from check_update import main  # noqa: E402

DATA_SHA = "b65854f575e3bd5658d1af9e10ab31f38c5c567e2b7e906ac8dc9d75d4b1aa67"
CANARY = "CANARY-SECRET-VALUE"
CST = timezone(timedelta(hours=8))


def snap(**overrides):
    base = {
        "title": "谱梦 · 进度监控",
        "updated_at": "2026-11-06 08:07 Asia/Shanghai",
        "source_updated_at": "2026-11-06 08:06 Asia/Shanghai",
        "refresh_seconds": 30,
        "decisions": [{"id": "d1", "title": "决定甲", "note": "说明"}],
        "today": {"doing": [{"id": "t1", "title": "事项甲", "note": "原说明", "blocker": "缺材料"}]},
        "timeline": [{"date": "2026-11-06", "did": ["做了甲"], "closed": [], "opened": []}],
        "metrics": {"songs_on_platform_approx": 1, "pm_ids_count": 1, "feishu_tables": {"play_snapshots": 3, "songs": 1, "artist_albums": 1}},
    }
    base.update(overrides)
    return base


def write_json(directory: Path, name: str, obj) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def approval_for(baseline, candidate, **extra):
    summary = summarize_diff(baseline, candidate)
    body = {
        "approved_at": "2026-11-06T09:10:00+08:00",
        "approver": "liu",
        "candidate_semantic_sha256": semantic_sha256(candidate),
        "large_change_confirmed": True if summary["large"] else False,
        "summary_sha256": sha256_json(summary),
    }
    body.update(extra)
    return body


def run(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    text = buffer.getvalue()
    return code, json.loads(text), text


class UpdateGateTests(unittest.TestCase):
    def setUp(self):
        self._env = {
            "PUMENG_SKIP_APPROVAL": os.environ.pop("PUMENG_SKIP_APPROVAL", None),
            "PUMENG_ALLOW_PRODUCTION_PUBLISH": os.environ.pop("PUMENG_ALLOW_PRODUCTION_PUBLISH", None),
        }

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_published_data_file_is_not_rewritten(self):
        digest = hashlib.sha256((ROOT / "data.json").read_bytes()).hexdigest()
        self.assertEqual(digest, DATA_SHA)

    def test_timestamp_noise_is_not_a_change_and_blocker_is(self):
        base = snap()
        noisy = snap(updated_at="2026-11-06 21:00 Asia/Shanghai", source_updated_at="1999-01-01 00:00", refresh_seconds=5)
        summary = summarize_diff(base, noisy)
        self.assertFalse(summary["semantic_change"])
        self.assertEqual(summary["ignored_changes"], ["refresh_seconds", "source_updated_at", "updated_at"])
        self.assertEqual(semantic_sha256(base), semantic_sha256(noisy))
        changed = snap()
        changed["today"]["doing"][0]["blocker"] = "换了阻塞原因"
        diff = summarize_diff(base, changed)
        self.assertTrue(diff["semantic_change"])
        self.assertFalse(diff["large"])
        self.assertTrue(any(path.endswith(".blocker") for path in diff["field_changes"]))

    def test_nested_timestamp_is_not_in_the_ignore_set(self):
        base = snap()
        changed = snap()
        changed["today"]["doing"][0]["updated_at"] = "2026-11-06 09:00"
        diff = summarize_diff(base, changed)
        self.assertTrue(diff["semantic_change"])
        self.assertIn("updated_at", SEMANTIC_IGNORE_KEYS)

    def test_reorder_is_semantic_but_not_large_and_metrics_are_large(self):
        base = snap()
        base["today"]["doing"].append({"id": "t2", "title": "事项乙", "note": "二"})
        reordered = snap()
        reordered["today"]["doing"] = [
            {"id": "t2", "title": "事项乙", "note": "二"},
            {"id": "t1", "title": "事项甲", "note": "原说明", "blocker": "缺材料"},
        ]
        diff = summarize_diff(base, reordered)
        self.assertTrue(diff["semantic_change"])
        self.assertTrue(diff["order_changes"])
        self.assertFalse(diff["large"])
        metrics = snap()
        metrics["metrics"]["songs_on_platform_approx"] = 2
        big = summarize_diff(base, metrics)
        self.assertIn("metrics", big["large_reasons"])

    def test_three_identity_changes_are_large(self):
        base = snap()
        base["today"]["doing"] = [{"id": f"t{i}", "title": str(i)} for i in range(3)]
        changed = snap()
        changed["today"]["doing"] = []
        diff = summarize_diff(base, changed)
        self.assertIn("identity", diff["large_reasons"])

    def test_slots_match_beijing_hours_only(self):
        self.assertEqual(BEIJING_HOURS, {9, 12, 15, 18, 21})
        self.assertEqual(SLOT_TOLERANCE_MINUTES, 15)
        for hour in (9, 12, 15, 18, 21):
            center = datetime(2026, 11, 6, hour, 0, tzinfo=CST)
            self.assertTrue(is_beijing_slot(center))
            self.assertTrue(is_beijing_slot(center + timedelta(minutes=15)))
            self.assertTrue(is_beijing_slot(center - timedelta(minutes=15)))
            self.assertFalse(is_beijing_slot(center + timedelta(minutes=16)))
            self.assertFalse(is_beijing_slot(center - timedelta(minutes=16)))
            self.assertFalse(is_beijing_slot(center.replace(minute=59)))
        self.assertFalse(is_beijing_slot(datetime(2026, 11, 6, 8, 7, tzinfo=CST)))
        self.assertFalse(is_beijing_slot(datetime(2026, 11, 6, 0, 20, tzinfo=CST)))
        self.assertTrue(is_beijing_slot(datetime(2026, 11, 6, 1, 0, tzinfo=timezone.utc)))
        self.assertTrue(is_beijing_slot(datetime(2026, 11, 6, 0, 50, tzinfo=timezone.utc)))
        self.assertFalse(is_beijing_slot(datetime(2026, 11, 6, 0, 30, tzinfo=timezone.utc)))
        with self.assertRaises(ValueError):
            is_beijing_slot(datetime(2026, 11, 6, 9, 0))

    def test_manual_and_scheduled_share_the_same_judgment(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            changed = snap()
            changed["today"]["doing"][0]["note"] = "改了说明"
            cand = write_json(tmp, "cand.json", changed)
            out_a = tmp / "a"
            out_b = tmp / "b"
            code_a, body_a, _ = run(["--baseline", str(base), "--candidate", str(cand), "--trigger", "manual", "--now", "2026-11-06T10:30:00+08:00", "--out", str(out_a)])
            code_b, body_b, _ = run(["--baseline", str(base), "--candidate", str(cand), "--trigger", "scheduled", "--now", "2026-11-06T09:05:00+08:00", "--out", str(out_b)])
            self.assertEqual(code_a, 0)
            self.assertEqual(code_b, 0)
            self.assertEqual(body_a["status"], "candidate_ready")
            self.assertEqual(body_b["status"], "candidate_ready")
            self.assertEqual(body_a["summary_sha256"], body_b["summary_sha256"])
            self.assertEqual(body_a["candidate_semantic_sha256"], body_b["candidate_semantic_sha256"])
            self.assertFalse(body_a["baseline_advanced"])
            self.assertFalse((out_a / "state" / "baseline.json").exists())

    def test_scheduled_outside_slot_does_not_emit_a_candidate(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            changed = snap()
            changed["decisions"][0]["title"] = "改了决定"
            cand = write_json(tmp, "cand.json", changed)
            out = tmp / "out"
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand), "--trigger", "scheduled", "--now", "2026-11-06T08:07:00+08:00", "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(body["status"], "outside_slot")
            self.assertTrue(body["would_change"])
            self.assertFalse((out / "candidates").exists())

    def test_invalid_candidate_keeps_the_success_baseline_and_writes_retry(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            out = tmp / "out"
            code, _, _ = run(["--baseline", str(base), "--seed-baseline", "--out", str(out), "--now", "2026-11-06T09:00:00+08:00"])
            self.assertEqual(code, 0)
            state = (out / "state" / "baseline.json").read_bytes()
            bad = tmp / "bad.json"
            bad.write_text("{not json", encoding="utf-8")
            code, body, _ = run(["--baseline", str(base), "--candidate", str(bad), "--trigger", "manual", "--now", "2026-11-06T10:00:00+08:00", "--out", str(out)])
            self.assertEqual(code, 3)
            self.assertEqual(body["status"], "invalid_candidate")
            self.assertTrue(body["retryable"])
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), state)
            retry = json.loads((out / "retry" / "last_failure.json").read_text(encoding="utf-8"))
            self.assertEqual(retry["error_type"], "JSONDecodeError")
            self.assertNotIn("not json", json.dumps(retry))

    def test_missing_stale_and_large_approval_do_not_advance(self):
        with self.case_dir() as tmp:
            base_obj = snap()
            base = write_json(tmp, "base.json", base_obj)
            changed = snap()
            changed["metrics"]["pm_ids_count"] = 9
            cand = write_json(tmp, "cand.json", changed)
            out = tmp / "out"
            run(["--baseline", str(base), "--seed-baseline", "--out", str(out), "--now", "2026-11-06T09:00:00+08:00"])
            seeded = (out / "state" / "baseline.json").read_bytes()
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand), "--trigger", "manual", "--simulate", "--now", "2026-11-06T11:00:00+08:00", "--out", str(out)])
            self.assertEqual(code, 4)
            self.assertEqual(body["status"], "missing_approval")
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), seeded)

            stale = approval_for(base_obj, snap())
            stale_path = write_json(tmp, "stale.json", stale)
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand), "--approval", str(stale_path), "--trigger", "manual", "--simulate", "--now", "2026-11-06T11:00:00+08:00", "--out", str(out)])
            self.assertEqual(body["status"], "stale_approval")
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), seeded)

            unconfirmed = approval_for(base_obj, changed, large_change_confirmed=False)
            no_flag = write_json(tmp, "nofield.json", unconfirmed)
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand), "--approval", str(no_flag), "--trigger", "scheduled", "--simulate", "--now", "2026-11-06T12:10:00+08:00", "--out", str(out)])
            self.assertEqual(body["status"], "large_change_unconfirmed")
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), seeded)
            self.assertFalse((out / "simulated").exists())

            good = write_json(tmp, "good.json", approval_for(base_obj, changed))
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand), "--approval", str(good), "--trigger", "manual", "--simulate", "--now", "2026-11-06T16:00:00+08:00", "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertEqual(body["status"], "simulated")
            self.assertTrue(body["baseline_advanced"])
            self.assertNotEqual((out / "state" / "baseline.json").read_bytes(), seeded)
            receipt = json.loads(next(iter((out / "simulated").rglob("receipt.json"))).read_text(encoding="utf-8"))
            self.assertFalse(receipt["production"])
            self.assertTrue(receipt["isolated"])
            advanced = (out / "state" / "baseline.json").read_bytes()

            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand), "--approval", str(stale_path), "--trigger", "manual", "--simulate", "--now", "2026-11-06T18:00:00+08:00", "--out", str(out)])
            self.assertEqual(body["status"], "stale_approval")
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), advanced)

    def test_bypass_and_publish_are_refused_without_leaking_the_canary(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            out = tmp / "out"
            run(["--baseline", str(base), "--seed-baseline", "--out", str(out), "--now", "2026-11-06T09:00:00+08:00"])
            seeded = (out / "state" / "baseline.json").read_bytes()
            os.environ["PUMENG_SKIP_APPROVAL"] = CANARY
            os.environ["PUMENG_ALLOW_PRODUCTION_PUBLISH"] = CANARY
            code, body, text = run(["--baseline", str(base), "--candidate", str(base), "--publish", "--simulate", "--out", str(out), "--now", "2026-11-06T09:00:00+08:00"])
            self.assertEqual(code, 5)
            self.assertEqual(body["status"], "bypass_rejected")
            self.assertNotIn(CANARY, text)
            self.assertNotIn(CANARY, json.dumps(body))
            blob = "\n".join(path.read_text(encoding="utf-8") for path in out.rglob("*.json"))
            self.assertNotIn(CANARY, blob)
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), seeded)

            del os.environ["PUMENG_SKIP_APPROVAL"]
            code, body, text = run(["--baseline", str(base), "--candidate", str(base), "--publish", "--out", str(out), "--now", "2026-11-06T09:00:00+08:00"])
            self.assertEqual(body["status"], "production_publish_disabled")
            self.assertNotIn(CANARY, text)
            self.assertFalse((out / "simulated").exists())
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), seeded)

            code, body, _ = run(["--baseline", str(base), "--bypass-approval", "--out", str(out), "--now", "2026-11-06T09:00:00+08:00"])
            self.assertEqual(body["status"], "bypass_rejected")

    def test_naive_now_and_missing_candidate_do_not_seed_or_advance(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            out = tmp / "out"
            code, body, _ = run(["--baseline", str(base), "--candidate", str(base), "--now", "2026-11-06T09:00:00", "--out", str(out)])
            self.assertEqual(code, 2)
            self.assertEqual(body["status"], "invalid_now")
            self.assertFalse((out / "state").exists())
            code, body, _ = run(["--baseline", str(base), "--trigger", "scheduled", "--now", "2026-11-06T09:00:00+08:00", "--out", str(out)])
            self.assertEqual(body["status"], "missing_candidate")
            self.assertTrue((out / "retry" / "last_failure.json").exists())
            self.assertFalse((out / "state").exists())

    def test_same_candidate_can_be_simulated_once_and_not_by_an_older_approval(self):
        with self.case_dir() as tmp:
            base_obj = snap()
            base = write_json(tmp, "base.json", base_obj)
            first = snap()
            first["today"]["doing"][0]["eta"] = "稍后"
            second = snap()
            second["today"]["doing"][0]["eta"] = "更晚"
            cand1 = write_json(tmp, "c1.json", first)
            cand2 = write_json(tmp, "c2.json", second)
            out = tmp / "out"
            good = write_json(tmp, "ok.json", approval_for(base_obj, first))
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand1), "--approval", str(good), "--trigger", "manual", "--simulate", "--now", "2026-11-06T15:00:00+08:00", "--out", str(out)])
            self.assertEqual(body["status"], "simulated")
            state = (out / "state" / "baseline.json").read_bytes()
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand1), "--approval", str(good), "--trigger", "manual", "--simulate", "--now", "2026-11-06T15:30:00+08:00", "--out", str(out)])
            self.assertEqual(body["status"], "simulated")
            self.assertFalse(body["baseline_advanced"])
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), state)
            code, body, _ = run(["--baseline", str(base), "--candidate", str(cand2), "--approval", str(good), "--trigger", "scheduled", "--simulate", "--now", "2026-11-06T21:00:00+08:00", "--out", str(out)])
            self.assertEqual(body["status"], "stale_approval")
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), state)

    def test_empty_object_is_a_real_diff_and_scripts_cannot_publish(self):
        summary = summarize_diff(snap(), {})
        self.assertTrue(summary["semantic_change"])
        self.assertTrue(summary["large"])
        forbidden = {"urllib", "subprocess", "socket", "http", "requests", "smtplib"}
        for path in (ROOT / "scripts").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".")[0] for alias in node.names}
                    self.assertFalse(names & forbidden, path.name)
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], forbidden, path.name)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("api.github.com", text)
            self.assertNotIn("git push", text)
        self.assertFalse((ROOT / ".github" / "workflows").exists())

    def case_dir(self):
        return tempfile_cm()


class tempfile_cm:
    def __enter__(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.__enter__())

    def __exit__(self, exc_type, exc, tb):
        return self._tmp.__exit__(exc_type, exc, tb)


if __name__ == "__main__":
    unittest.main()
