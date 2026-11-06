import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from check_update import main  # noqa: E402
from publish_paths import PATHS, attempt, list_paths  # noqa: E402
from test_update_gate import CANARY, approval_for, run, snap, write_json  # noqa: E402


class PublishPathTests(unittest.TestCase):
    def setUp(self):
        self._skip = os.environ.pop("PUMENG_SKIP_APPROVAL", None)
        self._allow = os.environ.pop("PUMENG_ALLOW_PRODUCTION_PUBLISH", None)

    def tearDown(self):
        if self._skip is None:
            os.environ.pop("PUMENG_SKIP_APPROVAL", None)
        else:
            os.environ["PUMENG_SKIP_APPROVAL"] = self._skip
        if self._allow is None:
            os.environ.pop("PUMENG_ALLOW_PRODUCTION_PUBLISH", None)
        else:
            os.environ["PUMENG_ALLOW_PRODUCTION_PUBLISH"] = self._allow

    def test_registry_does_not_treat_routine_text_as_a_gate(self):
        ids = [item["id"] for item in PATHS]
        self.assertIn("publish_sh", ids)
        self.assertIn("routine_text_freeze", ids)
        self.assertIn("manual_publish_flag", ids)
        for item in list_paths():
            self.assertFalse(item["routine_text_is_gate"])
            self.assertIn(item["production_control"], {"absent", "unknown"})
        freeze = attempt("routine_text_freeze", routine_freeze_text=True, invoke_external=True, publisher=lambda: (_ for _ in ()).throw(AssertionError("publisher")))
        script = attempt("publish_sh", routine_freeze_text=True, invoke_external=True, publisher=lambda: (_ for _ in ()).throw(AssertionError("publisher")))
        push = attempt("git_push_main", routine_freeze_text=True, invoke_external=True, publisher=lambda: (_ for _ in ()).throw(AssertionError("publisher")))
        self.assertFalse(freeze["covered"])
        self.assertEqual(freeze["code_gate"], "absent")
        self.assertFalse(script["covered"])
        self.assertEqual(script["coverage"], "uncovered_external")
        self.assertFalse(push["invoke_external_honored"])
        self.assertFalse(push["publisher_called"])
        self.assertFalse(push["called_network"])
        self.assertEqual(push["production_control"], "absent")

    def test_manual_and_scheduled_publish_flags_stay_refused_inside_the_slot(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            changed = snap()
            changed["today"]["doing"][0]["note"] = "手动也不发布"
            cand = write_json(tmp, "cand.json", changed)
            for trigger in ("manual", "scheduled"):
                out = tmp / trigger
                code, body, text = run([
                    "--baseline", str(base),
                    "--candidate", str(cand),
                    "--trigger", trigger,
                    "--publish",
                    "--simulate",
                    "--now", "2026-11-06T09:00:00+08:00",
                    "--out", str(out),
                ])
                self.assertEqual(code, 5, trigger)
                self.assertEqual(body["status"], "production_publish_disabled")
                self.assertFalse(body["production_publish"])
                self.assertFalse((out / "simulated").exists())
                self.assertFalse((out / "state").exists())
                self.assertNotIn("CANARY", text)

    def test_manual_bypass_and_allow_env_do_not_open_publish(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            out = tmp / "out"
            os.environ["PUMENG_SKIP_APPROVAL"] = CANARY
            os.environ["PUMENG_ALLOW_PRODUCTION_PUBLISH"] = CANARY
            code, body, text = run([
                "--baseline", str(base),
                "--trigger", "manual",
                "--publish",
                "--now", "2026-11-06T21:10:00+08:00",
                "--out", str(out),
            ])
            self.assertEqual(code, 5)
            self.assertEqual(body["status"], "bypass_rejected")
            self.assertNotIn(CANARY, text)
            self.assertNotIn(CANARY, json.dumps(body))
            del os.environ["PUMENG_SKIP_APPROVAL"]
            code, body, text = run([
                "--baseline", str(base),
                "--trigger", "manual",
                "--bypass-approval",
                "--simulate",
                "--now", "2026-11-06T12:00:00+08:00",
                "--out", str(out),
            ])
            self.assertEqual(body["status"], "bypass_rejected")
            self.assertFalse((out / "simulated").exists())

    def test_manual_simulate_still_needs_a_current_approval(self):
        with self.case_dir() as tmp:
            base_obj = snap()
            base = write_json(tmp, "base.json", base_obj)
            changed = snap()
            changed["decisions"][0]["note"] = "改一句"
            cand = write_json(tmp, "cand.json", changed)
            out = tmp / "out"
            code, body, _ = run([
                "--baseline", str(base),
                "--candidate", str(cand),
                "--trigger", "manual",
                "--simulate",
                "--now", "2026-11-06T10:40:00+08:00",
                "--out", str(out),
            ])
            self.assertEqual(code, 4)
            self.assertEqual(body["status"], "missing_approval")
            self.assertFalse((out / "state").exists())
            good = write_json(tmp, "ok.json", approval_for(base_obj, changed))
            code, body, _ = run([
                "--baseline", str(base),
                "--candidate", str(cand),
                "--approval", str(good),
                "--trigger", "manual",
                "--simulate",
                "--now", "2026-11-06T10:40:00+08:00",
                "--out", str(out),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(body["status"], "simulated")
            self.assertFalse(body["production_publish"])
            receipt = json.loads(next((out / "simulated").rglob("receipt.json")).read_text(encoding="utf-8"))
            self.assertFalse(receipt["production"])

    def test_forged_now_can_change_the_slot_and_still_cannot_publish(self):
        with self.case_dir() as tmp:
            base = write_json(tmp, "base.json", snap())
            changed = snap()
            changed["today"]["doing"][0]["eta"] = "稍后"
            cand = write_json(tmp, "cand.json", changed)
            outside = tmp / "out-slot"
            code, body, _ = run([
                "--baseline", str(base),
                "--candidate", str(cand),
                "--trigger", "scheduled",
                "--now", "2026-11-06T09:16:00+08:00",
                "--out", str(outside),
            ])
            self.assertEqual(body["status"], "outside_slot")
            self.assertFalse((outside / "candidates").exists())
            inside = tmp / "in-slot"
            code, body, _ = run([
                "--baseline", str(base),
                "--candidate", str(cand),
                "--trigger", "scheduled",
                "--now", "2026-11-06T08:50:00+08:00",
                "--out", str(inside),
            ])
            self.assertEqual(body["status"], "candidate_ready")
            self.assertFalse(body["baseline_advanced"])
            code, body, _ = run([
                "--baseline", str(base),
                "--candidate", str(cand),
                "--trigger", "scheduled",
                "--publish",
                "--now", "2026-11-06T08:50:00+08:00",
                "--out", str(tmp / "nope"),
            ])
            self.assertEqual(code, 5)
            self.assertEqual(body["status"], "production_publish_disabled")

    def test_list_paths_is_not_a_publish_and_external_script_is_absent(self):
        code, body, _ = run(["--list-paths"])
        self.assertEqual(code, 0)
        self.assertFalse(body["production_control_configured"])
        listed = {item["id"]: item for item in body["paths"]}
        self.assertEqual(listed["publish_sh"]["coverage"], "uncovered_external")
        self.assertEqual(listed["contents_api"]["code_gate"], "absent")
        self.assertEqual(listed["pull_request_merge"]["production_control"], "absent")
        self.assertFalse(listed["routine_text_freeze"]["routine_text_is_gate"])
        with self.case_dir() as tmp:
            code, body, _ = run(["--list-paths", "--publish", "--out", str(tmp / "out")])
        self.assertEqual(code, 5)
        self.assertEqual(body["status"], "production_publish_disabled")
        scripts = list(ROOT.rglob("publish.sh"))
        self.assertEqual(scripts, [ROOT / "scripts" / "replacement" / "publish.sh"])
        replacement = scripts[0].read_text(encoding="utf-8")
        self.assertNotIn("gh auth token", replacement)
        self.assertNotIn("git push", replacement)

    def case_dir(self):
        from test_update_gate import tempfile_cm
        return tempfile_cm()


if __name__ == "__main__":
    unittest.main()
