import json
import os
import stat
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from replacement.build_snapshot import build_snapshot, scan_text  # noqa: E402
from replacement.safe_publish import main  # noqa: E402
from test_update_gate import CANARY, approval_for, snap, write_json  # noqa: E402

CST = timezone(timedelta(hours=8))


def tasks_doc():
    return {
        "updated_at": "2026-11-06 08:06 Asia/Shanghai",
        "lines": {
            "pumeng": {
                "doing": [{"id": "t1", "owner": "甲", "title": "事项甲", "note": "一句说明", "line": "pumeng"}],
                "todo": [],
                "paused": [],
                "done_today": [],
            },
            "douyin": {"doing": [], "todo": [], "paused": [], "done_today": []},
        },
        "decisions": [{"id": "d1", "title": "决定甲", "note": "一句", "owner": "乙"}],
        "timeline": [{"date": "2026-11-06", "did": ["做了甲"], "closed": [], "opened": []}],
        "metrics": {
            "songs_on_platform_approx": 3,
            "feishu_tables": {"play_snapshots": 1, "songs": 1, "artist_albums": 1},
            "pm_ids": ["PM-A", "PM-B"],
        },
    }


def run_publish(argv):
    from io import StringIO
    from contextlib import redirect_stdout
    buffer = StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


class ReplacementTests(unittest.TestCase):
    def test_schema_hides_pm_ids_and_flattens_lines(self):
        built = build_snapshot(tasks_doc(), datetime(2026, 11, 6, 8, 7, tzinfo=CST))
        self.assertEqual(built["metrics"]["pm_ids_count"], 2)
        self.assertNotIn("pm_ids", built["metrics"])
        self.assertEqual(built["today"]["doing"][0]["line_label"], "谱梦")
        self.assertEqual(built["source_updated_at"], "2026-11-06 08:06 Asia/Shanghai")
        self.assertEqual(built["updated_at"], "2026-11-06 08:07 Asia/Shanghai")
        self.assertFalse(built["_scan"]["historical_detectors_available"])
        self.assertEqual(scan_text("[REDACTED_ACCOUNT_PATTERN]"), [])

    def test_sensitive_material_fails_closed_without_echoing_the_value(self):
        secret = "sk-" + "A" * 20
        raw = tasks_doc()
        raw["decisions"][0]["note"] = "见 " + secret
        with self.assertRaises(Exception) as caught:
            build_snapshot(raw, datetime(2026, 11, 6, 9, 0, tzinfo=CST))
        self.assertIn("sk_token", caught.exception.rule_ids)
        self.assertNotIn(secret, str(caught.exception))

    def test_pipeline_rejects_secret_and_keeps_baseline(self):
        with self.case_dir() as tmp:
            base_obj = snap()
            base = write_json(tmp, "base.json", base_obj)
            out = tmp / "out"
            from check_update import main as check_main
            from io import StringIO
            from contextlib import redirect_stdout
            with redirect_stdout(StringIO()):
                self.assertEqual(check_main(["--baseline", str(base), "--seed-baseline", "--out", str(out), "--now", "2026-11-06T09:00:00+08:00"]), 0)
            state = (out / "state" / "baseline.json").read_bytes()
            secret = "ghp_" + "b" * 20
            raw = tasks_doc()
            raw["decisions"][0]["note"] = secret
            task = write_json(tmp, "tasks.json", raw)
            code, body = run_publish(["--tasks", str(task), "--baseline", str(base), "--trigger", "manual", "--now", "2026-11-06T09:05:00+08:00", "--out", str(out)])
            self.assertEqual(code, 3)
            self.assertEqual(body["status"], "sensitive_rejected")
            self.assertEqual(body["rule_ids"], ["github_token"])
            self.assertNotIn(secret, json.dumps(body))
            self.assertFalse(body["read_gh_token"])
            self.assertEqual((out / "state" / "baseline.json").read_bytes(), state)
            self.assertFalse((out / "built-candidate.json").exists())

    def test_old_style_shell_does_not_call_git_or_gh(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", build_snapshot(tasks_doc(), datetime(2026, 11, 6, 8, 7, tzinfo=CST)))
            # baseline file must not contain the private _scan key
            payload = json.loads(base.read_text(encoding="utf-8"))
            payload.pop("_scan", None)
            base.write_text(json.dumps(payload), encoding="utf-8")
            task = write_json(tmp, "tasks.json", tasks_doc())
            bindir = tmp / "bin"
            bindir.mkdir()
            for name in ("git", "gh"):
                prog = bindir / name
                prog.write_text("#!/bin/sh\necho called-%s >> \"$MARK\"\nexit 99\n" % name, encoding="utf-8")
                prog.chmod(prog.stat().st_mode | stat.S_IEXEC)
            mark = tmp / "called"
            env = os.environ.copy()
            env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
            env["MARK"] = str(mark)
            env["GH_TOKEN"] = CANARY
            env["GITHUB_TOKEN"] = CANARY
            env["DASHBOARD_BRANCH"] = "main"
            proc = subprocess.run(
                ["bash", str(ROOT / "scripts/replacement/publish.sh"), "--tasks", str(task), "--baseline", str(base), "--trigger", "scheduled", "--now", "2026-11-06T09:00:00+08:00", "--out", str(tmp / "out")],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertFalse(mark.exists())
            self.assertNotIn(CANARY, proc.stdout)
            self.assertNotIn("gh auth token", (ROOT / "scripts/replacement/publish.sh").read_text(encoding="utf-8"))
            self.assertNotIn("git push", (ROOT / "scripts/replacement/safe_publish.py").read_text(encoding="utf-8"))
            body = json.loads(proc.stdout)
            self.assertEqual(body["status"], "no_semantic_change")
            self.assertFalse(body["read_gh_token"])

    def test_manual_and_scheduled_share_judgment_and_stale_approval_does_not_advance(self):
        with self.case_dir() as tmp:
            first = build_snapshot(tasks_doc(), datetime(2026, 11, 6, 8, 7, tzinfo=CST))
            first.pop("_scan", None)
            base = write_json(tmp, "base.json", first)
            changed = tasks_doc()
            changed["decisions"][0]["title"] = "决定甲改了"
            task = write_json(tmp, "tasks.json", changed)
            manual = tmp / "manual"
            scheduled = tmp / "scheduled"
            code_m, body_m = run_publish(["--tasks", str(task), "--baseline", str(base), "--trigger", "manual", "--now", "2026-11-06T10:40:00+08:00", "--out", str(manual)])
            code_s, body_s = run_publish(["--tasks", str(task), "--baseline", str(base), "--trigger", "scheduled", "--now", "2026-11-06T09:05:00+08:00", "--out", str(scheduled)])
            self.assertEqual(code_m, 0)
            self.assertEqual(code_s, 0)
            self.assertEqual(body_m["status"], "candidate_ready")
            self.assertEqual(body_s["status"], "candidate_ready")
            self.assertEqual(body_m["summary_sha256"], body_s["summary_sha256"])
            self.assertFalse((manual / "state" / "baseline.json").exists())
            built = json.loads((manual / "built-candidate.json").read_text(encoding="utf-8"))
            stale = write_json(tmp, "stale.json", approval_for(first, snap()))
            code, body = run_publish(["--tasks", str(task), "--baseline", str(base), "--approval", str(stale), "--trigger", "manual", "--simulate", "--now", "2026-11-06T10:40:00+08:00", "--out", str(tmp / "sim")])
            self.assertEqual(body["status"], "stale_approval")
            self.assertFalse((tmp / "sim" / "state").exists())
            good = write_json(tmp, "ok.json", approval_for(first, built))
            from check_update import main as check_main
            from io import StringIO
            from contextlib import redirect_stdout
            with redirect_stdout(StringIO()):
                check_main(["--baseline", str(base), "--seed-baseline", "--out", str(tmp / "sim"), "--now", "2026-11-06T09:00:00+08:00"])
            seeded = (tmp / "sim" / "state" / "baseline.json").read_bytes()
            code, body = run_publish(["--tasks", str(task), "--baseline", str(base), "--approval", str(good), "--trigger", "scheduled", "--simulate", "--now", "2026-11-06T12:00:00+08:00", "--out", str(tmp / "sim")])
            self.assertEqual(code, 0)
            self.assertEqual(body["status"], "simulated")
            self.assertTrue(body["baseline_advanced"])
            self.assertNotEqual((tmp / "sim" / "state" / "baseline.json").read_bytes(), seeded)
            bad = tmp / "bad.json"
            bad.write_text("{", encoding="utf-8")
            advanced = (tmp / "sim" / "state" / "baseline.json").read_bytes()
            code, body = run_publish(["--tasks", str(bad), "--baseline", str(base), "--trigger", "manual", "--now", "2026-11-06T12:00:00+08:00", "--out", str(tmp / "sim")])
            self.assertEqual(body["status"], "invalid_tasks")
            self.assertEqual((tmp / "sim" / "state" / "baseline.json").read_bytes(), advanced)

    def test_production_flags_are_refused_and_preview_does_not_publish(self):
        with self.case_dir() as tmp:
            task = write_json(tmp, "tasks.json", tasks_doc())
            code, body = run_publish(["--tasks", str(task), "--trigger", "manual", "--push", "--contents-api", "--now", "2026-11-06T09:00:00+08:00", "--out", str(tmp / "out")])
            self.assertEqual(code, 5)
            self.assertEqual(body["status"], "production_publish_disabled")
            proc = subprocess.run(
                ["bash", str(ROOT / "scripts/replacement/preview.sh"), "--tasks", str(task), "--now", "2026-11-06T09:00:00+08:00", "--out", str(tmp / "preview")],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            preview = json.loads(proc.stdout)
            self.assertEqual(preview["status"], "preview_built")
            self.assertFalse(preview["production_publish"])
            text = (ROOT / "scripts/replacement/preview.sh").read_text(encoding="utf-8")
            self.assertNotIn("git", text)
            self.assertNotIn("gh", text)

    def case_dir(self):
        from test_update_gate import tempfile_cm
        return tempfile_cm()


if __name__ == "__main__":
    unittest.main()
