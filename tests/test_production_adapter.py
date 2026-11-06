import hashlib
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from replacement.build_snapshot import build_snapshot  # noqa: E402
from replacement.production_adapter import (  # noqa: E402
    GitPagesPublisher,
    mint_release,
    plan_push,
    run_controlled_publish,
)
from replacement.safe_publish import main  # noqa: E402
from test_update_gate import CANARY  # noqa: E402

CST = timezone(timedelta(hours=8))
RUNNING = "a" * 40


def tasks():
    return {
        "updated_at": "2026-11-06 08:06 Asia/Shanghai",
        "lines": {"pumeng": {"doing": [{"id": "t1", "owner": "甲", "title": "事项甲", "note": "说明", "line": "pumeng"}]}},
        "decisions": [{"id": "d1", "title": "决定甲", "note": "一句", "owner": "乙"}],
        "timeline": [{"date": "2026-11-06", "did": ["做了甲"], "closed": [], "opened": []}],
        "metrics": {"songs_on_platform_approx": 3, "pm_ids": ["PM-A"]},
    }


def built_at(hour, minute, raw=None):
    data = build_snapshot(raw or tasks(), datetime(2026, 11, 6, hour, minute, tzinfo=CST))
    data.pop("_scan", None)
    return data


class FakePublisher:
    uses_network = False

    def __init__(self, body: bytes):
        self.body = body
        self.pushes = 0
        self.verifies = 0
        self.fail_pushes = 0
        self.fail_verifies = 0

    def push_main(self, **_kwargs):
        self.pushes += 1
        if self.fail_pushes:
            self.fail_pushes -= 1
            return {"git_push_ok": False, "pages_verified": False}
        return {"git_push_ok": True, "pages_verified": False, "remote_commit": "fakecommit"}

    def verify_pages(self, **kwargs):
        self.verifies += 1
        if self.fail_verifies:
            self.fail_verifies -= 1
            return {"git_push_ok": True, "pages_verified": False}
        ok = kwargs.get("expected_sha256") == hashlib.sha256(self.body).hexdigest()
        return {"git_push_ok": True, "pages_verified": ok}


def install(enabled=True):
    return {
        "installed": True,
        "repo": "iuei/pumeng-dashboard",
        "branch": "main",
        "remote": "https://github.com/iuei/pumeng-dashboard.git",
        "pages_data_url": "https://iuei.github.io/pumeng-dashboard/data.json",
        "network_publisher": enabled,
    }


def release_for(baseline, candidate, **extra):
    from pumeng_update import semantic_sha256, sha256_json, summarize_diff
    summary = summarize_diff(baseline, candidate)
    body = {
        "accepted_by": "haole",
        "approval_id": "acc-test-1",
        "approved_code_sha": RUNNING,
        "approver": "liu",
        "branch": "main",
        "candidate_semantic_sha256": semantic_sha256(candidate),
        "large_change_confirmed": bool(summary["large"]),
        "repo": "iuei/pumeng-dashboard",
        "summary_sha256": sha256_json(summary),
    }
    body.update(extra)
    return body


def run_main(argv):
    from io import StringIO
    from contextlib import redirect_stdout
    buffer = StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


class ProductionAdapterTests(unittest.TestCase):
    def test_release_cannot_be_minted_by_the_checker(self):
        with self.assertRaises(RuntimeError):
            mint_release(candidate_semantic_sha256="abc")

    def test_plan_push_has_no_token_and_rejects_credential_urls(self):
        argv = plan_push("https://github.com/iuei/pumeng-dashboard.git", "main")
        self.assertEqual(argv, ["git", "push", "https://github.com/iuei/pumeng-dashboard.git", "HEAD:main"])
        self.assertNotIn("x-access-token", " ".join(argv))
        with self.assertRaises(ValueError):
            plan_push("https://x-access-token:secret@github.com/iuei/pumeng-dashboard.git", "main")

    def test_success_advances_only_after_pages_verify_and_retry_is_idempotent(self):
        with self.case_dir() as tmp:
            baseline = built_at(8, 7)
            candidate = built_at(9, 0)
            candidate["decisions"][0]["title"] = "决定甲已改"
            body = json.dumps(candidate, ensure_ascii=False).encode("utf-8")
            fake = FakePublisher(body)
            fake.fail_pushes = 1
            common = dict(
                baseline=baseline,
                candidate=candidate,
                trigger="scheduled",
                now=datetime(2026, 11, 6, 9, 0, tzinfo=CST),
                install=install(),
                release=release_for(baseline, candidate),
                running_sha=RUNNING,
                out_dir=tmp,
                publisher=fake,
                candidate_bytes=body,
            )
            failed = run_controlled_publish(**common)
            self.assertEqual(failed["status"], "push_failed")
            self.assertFalse(failed["git_push_ok"])
            self.assertFalse(failed["pages_verified"])
            self.assertFalse((tmp / "state" / "baseline.json").exists())
            fake.fail_verifies = 1
            verified_fail = run_controlled_publish(**common)
            self.assertEqual(verified_fail["status"], "pages_verify_failed")
            self.assertTrue(verified_fail["git_push_ok"])
            self.assertFalse(verified_fail["pages_verified"])
            self.assertFalse(verified_fail["baseline_advanced"])
            self.assertFalse((tmp / "state" / "baseline.json").exists())
            ok = run_controlled_publish(**common)
            self.assertEqual(ok["status"], "published")
            self.assertTrue(ok["pages_verified"])
            self.assertTrue(ok["baseline_advanced"])
            self.assertFalse(ok["called_network"])
            again = run_controlled_publish(**common)
            self.assertEqual(again["status"], "no_semantic_change")
            self.assertEqual(fake.pushes, 3)

    def test_stale_large_slot_and_concurrency_do_not_publish(self):
        with self.case_dir() as tmp:
            baseline = built_at(8, 7)
            candidate = built_at(9, 0)
            candidate["metrics"]["songs_on_platform_approx"] = 9
            body = json.dumps(candidate).encode("utf-8")
            fake = FakePublisher(body)
            stale = release_for(baseline, built_at(8, 7))
            result = run_controlled_publish(
                baseline=baseline, candidate=candidate, trigger="manual",
                now=datetime(2026, 11, 6, 10, 40, tzinfo=CST), install=install(),
                release=stale, running_sha=RUNNING, out_dir=tmp, publisher=fake, candidate_bytes=body,
            )
            self.assertEqual(result["status"], "stale_release")
            self.assertEqual(fake.pushes, 0)
            unconfirmed = release_for(baseline, candidate, large_change_confirmed=False)
            result = run_controlled_publish(
                baseline=baseline, candidate=candidate, trigger="scheduled",
                now=datetime(2026, 11, 6, 9, 10, tzinfo=CST), install=install(),
                release=unconfirmed, running_sha=RUNNING, out_dir=tmp, publisher=fake, candidate_bytes=body,
            )
            self.assertEqual(result["status"], "large_change_unconfirmed")
            outside = run_controlled_publish(
                baseline=baseline, candidate=candidate, trigger="scheduled",
                now=datetime(2026, 11, 6, 8, 7, tzinfo=CST), install=install(),
                release=release_for(baseline, candidate), running_sha=RUNNING, out_dir=tmp, publisher=fake, candidate_bytes=body,
            )
            self.assertEqual(outside["status"], "outside_slot")
            manual = run_controlled_publish(
                baseline=baseline, candidate=candidate, trigger="manual",
                now=datetime(2026, 11, 6, 8, 7, tzinfo=CST), install=install(),
                release=release_for(baseline, candidate), running_sha=RUNNING, out_dir=tmp, publisher=fake, candidate_bytes=body,
            )
            self.assertEqual(manual["status"], "published")
            lock = tmp / "state" / "publish.lock"
            lock.parent.mkdir(parents=True, exist_ok=True)
            lock.write_text("held", encoding="utf-8")
            other = built_at(9, 0)
            other["decisions"][0]["title"] = "另一份"
            blocked = run_controlled_publish(
                baseline=baseline, candidate=other, trigger="manual",
                now=datetime(2026, 11, 6, 9, 0, tzinfo=CST), install=install(),
                release=release_for(baseline, other), running_sha=RUNNING, out_dir=tmp, publisher=fake,
                candidate_bytes=json.dumps(other).encode("utf-8"),
            )
            self.assertEqual(blocked["status"], "concurrent_run")
            self.assertTrue(lock.exists())

    def test_baseline_advance_failure_keeps_the_previous_file(self):
        with self.case_dir() as tmp:
            baseline = built_at(8, 7)
            candidate = built_at(9, 0)
            candidate["decisions"][0]["note"] = "改了"
            body = json.dumps(candidate).encode("utf-8")
            state = tmp / "state" / "baseline.json"
            state.parent.mkdir(parents=True)
            state.write_text('{"semantic_sha256":"old","pages_verified":false}\n', encoding="utf-8")
            before = state.read_bytes()
            result = run_controlled_publish(
                baseline=baseline, candidate=candidate, trigger="manual",
                now=datetime(2026, 11, 6, 9, 0, tzinfo=CST), install=install(),
                release=release_for(baseline, candidate), running_sha=RUNNING, out_dir=tmp,
                publisher=FakePublisher(body), candidate_bytes=body,
                before_advance=lambda: (_ for _ in ()).throw(RuntimeError("disk")),
            )
            self.assertEqual(result["status"], "baseline_advance_failed")
            self.assertTrue(result["pages_verified"])
            self.assertFalse(result["baseline_advanced"])
            self.assertEqual(state.read_bytes(), before)

    def test_cli_does_not_network_or_read_token_and_legacy_flags_cannot_bypass(self):
        import replacement.production_adapter as adapter
        calls = []
        def boom(*_args, **_kwargs):
            calls.append("real")
            raise AssertionError("real publisher used")
        old_run = adapter.subprocess_runner
        old_fetch = adapter.network_fetch
        adapter.subprocess_runner = boom
        adapter.network_fetch = boom
        os.environ["GH_TOKEN"] = CANARY
        try:
            with self.case_dir() as tmp:
                raw = tasks()
                raw["decisions"][0]["title"] = "决定甲需要发布"
                task = tmp / "tasks.json"
                task.write_text(json.dumps(raw), encoding="utf-8")
                base = built_at(8, 7)
                base_path = tmp / "base.json"
                base_path.write_text(json.dumps(base), encoding="utf-8")
                code, body = run_main([
                    "--tasks", str(task), "--baseline", str(base_path), "--trigger", "manual",
                    "--production", "--now", "2026-11-06T09:00:00+08:00", "--out", str(tmp / "out"),
                ])
                self.assertEqual(body["status"], "missing_install")
                self.assertEqual(calls, [])
                self.assertNotIn(CANARY, json.dumps(body))
                code, body = run_main([
                    "--tasks", str(task), "--baseline", str(base_path), "--publish", "--production",
                    "--now", "2026-11-06T09:00:00+08:00", "--out", str(tmp / "out2"),
                ])
                self.assertEqual(code, 5)
                self.assertEqual(body["status"], "legacy_flag_cannot_bypass")
                enabled = install(True)
                install_path = tmp / "install.json"
                install_path.write_text(json.dumps(enabled), encoding="utf-8")
                rel = release_for(base, built_at(9, 0, raw))
                # candidate at 09:00 differs by updated_at only, so no semantic change and no publisher
                rel_path = tmp / "release.json"
                rel_path.write_text(json.dumps(rel), encoding="utf-8")
                code, body = run_main([
                    "--tasks", str(task), "--baseline", str(base_path), "--trigger", "scheduled",
                    "--detect", "--install", str(install_path), "--release", str(rel_path),
                    "--running-sha", RUNNING, "--now", "2026-11-06T09:00:00+08:00", "--out", str(tmp / "detect"),
                ])
                self.assertEqual(body["status"], "detect_ready")
                self.assertTrue(body["would_publish"])
                self.assertFalse(body.get("publisher_invoked", False))
                self.assertEqual(calls, [])
                source = (ROOT / "scripts" / "replacement").read_text() if False else ""
                blob = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "scripts" / "replacement").glob("*.py"))
                blob += "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "scripts" / "replacement").glob("*.sh"))
                self.assertNotIn("gh auth token", blob)
                self.assertNotIn("x-access-token", blob)
                self.assertNotIn("GH_TOKEN", blob)
                self.assertNotIn("contents/", blob)
        finally:
            adapter.subprocess_runner = old_run
            adapter.network_fetch = old_fetch
            os.environ.pop("GH_TOKEN", None)

    def case_dir(self):
        from test_update_gate import tempfile_cm
        return tempfile_cm()


if __name__ == "__main__":
    unittest.main()
