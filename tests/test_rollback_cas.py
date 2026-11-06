"""Rollback compare-and-swap races. Inputs are synthetic.

The observer below is not the original prepush_race.py. That original only
recognizes a refspec starting with '+'. This one classifies the product's
update, delete, and recreate commands, injects one ordinary fast-forward
(or a non-forced create when main is absent), then executes the product
argv unchanged.
"""

import json
import os
import subprocess
import textwrap
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLISH_ONCE = ROOT / "scripts" / "replacement" / "operator" / "publish-once.sh"


def git_env():
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    env.pop("PUMENG_ALLOW_GITHUB_PUBLISH", None)
    return env


WRAPPER = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, subprocess, sys
    from pathlib import Path
    real = os.environ["PUMENG_REAL_GIT"]
    window = os.environ.get("PUMENG_RACE_WINDOW", "")
    log_path = Path(os.environ["PUMENG_RACE_LOG"])
    args = sys.argv[1:]

    def classify(argv):
        if "push" not in argv:
            return None
        lease = next((item for item in argv if item.startswith("--force-with-lease=refs/heads/main:")), None)
        if lease is None:
            return None
        expect = lease.split("refs/heads/main:", 1)[1]
        refspec = argv[-1]
        if refspec == ":refs/heads/main":
            return "delete"
        if expect == "":
            return "recreate"
        if refspec.endswith(":refs/heads/main"):
            return "update"
        return None

    def record(entry):
        rows = []
        if log_path.exists():
            rows = json.loads(log_path.read_text(encoding="utf-8"))
        rows.append(entry)
        log_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")

    kind = classify(args)
    already = False
    if log_path.exists():
        already = any(row.get("injected") and row.get("kind") == window for row in json.loads(log_path.read_text(encoding="utf-8")))
    injection = None
    if kind == window and not already:
        repo = args[args.index("-C") + 1]
        remote = args[args.index("push") + 2]
        if kind == "recreate":
            parent = subprocess.run([real, "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        else:
            parent = subprocess.run([real, "ls-remote", remote, "refs/heads/main"], capture_output=True, text=True).stdout.split()[0]
        tree = subprocess.run([real, "-C", repo, "rev-parse", parent + "^{tree}"], capture_output=True, text=True, check=True).stdout.strip()
        created = subprocess.run(
            [real, "-C", repo, "-c", "user.email=synth@example.invalid", "-c", "user.name=synth", "commit-tree", tree, "-p", parent, "-m", "synthetic foreign " + kind],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        pushed = subprocess.run([real, "-C", repo, "push", remote, created + ":refs/heads/main"], capture_output=True, text=True)
        injection = {
            "label": "semantic-equivalent-observer",
            "kind": kind,
            "foreign": created,
            "parent": parent,
            "refspec": created + ":refs/heads/main",
            "forced": False,
            "returncode": pushed.returncode,
            "stderr": pushed.stderr[-400:],
        }
    proc = subprocess.run([real, *args], capture_output=True)
    record({
        "label": "semantic-equivalent-observer",
        "kind": kind,
        "window": window,
        "injected": injection is not None,
        "product_argv": ["git", *args],
        "executed_argv": [real, *args],
        "argv_unchanged": True,
        "injection": injection,
        "returncode": proc.returncode,
        "stderr": proc.stderr.decode("utf-8", "replace")[-500:],
    })
    sys.stdout.buffer.write(proc.stdout)
    sys.stderr.buffer.write(proc.stderr)
    raise SystemExit(proc.returncode)
    """
)


class RollbackCasTests(unittest.TestCase):
    def test_operator_keeps_foreign_tip_in_each_rollback_window(self):
        import sys
        import tempfile
        sys.path.insert(0, str(ROOT / "tests"))
        from test_incremental_publish import IncrementalPublishTests, base_tasks

        helper = IncrementalPublishTests()
        helper.setUp()
        real_git = subprocess.check_output(["which", "git"], text=True).strip()
        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            wrapper = tmp / "git"
            wrapper.write_text(WRAPPER, encoding="utf-8")
            wrapper.chmod(0o755)
            reports = []
            for window in ("update", "delete", "recreate"):
                slot = tmp / window
                slot.mkdir()
                world = helper.make_root(slot)
                if window in {"delete", "recreate"}:
                    subprocess.run(
                        ["git", "--git-dir", str(world["bare"]), "config", "receive.denyNonFastForwards", "true"],
                        check=True,
                        env=git_env(),
                    )
                helper.bind_release(world, base_tasks("合成甲-回滚竞态"))
                world["pages"].write_bytes(b'{"synthetic":"mismatch"}\n')
                helper.open_network(world, True)
                log_path = tmp / f"{window}-race.json"
                env = git_env()
                env["PATH"] = str(tmp) + os.pathsep + env["PATH"]
                env["PUMENG_REAL_GIT"] = real_git
                env["PUMENG_RACE_WINDOW"] = window
                env["PUMENG_RACE_LOG"] = str(log_path)
                env["PUMENG_ROOT"] = str(world["root"])
                env["PUMENG_CONFIRM_PUBLISH"] = "1"
                env["PUMENG_PUBLISH_NOW"] = "2026-11-06T15:00:00+08:00"
                completed = subprocess.run(["bash", str(PUBLISH_ONCE)], capture_output=True, text=True, env=env)
                status_path = world["root"] / "pumeng-update-out" / "production" / "status.json"
                status = json.loads(status_path.read_text(encoding="utf-8"))
                install = json.loads((world["root"] / "pumeng-release" / "install.json").read_text(encoding="utf-8"))
                calls = json.loads(log_path.read_text(encoding="utf-8"))
                injected = next(row for row in calls if row.get("injected"))
                foreign = injected["injection"]["foreign"]
                final = subprocess.run(
                    ["git", "ls-remote", world["remote"], "refs/heads/main"],
                    capture_output=True, text=True, env=git_env(), check=True,
                ).stdout.split()[0]
                local = subprocess.run(
                    ["git", "-C", str(world["work"]), "rev-parse", "HEAD"],
                    capture_output=True, text=True, env=git_env(), check=True,
                ).stdout.strip()
                self.assertEqual(completed.returncode, 3, completed.stdout + completed.stderr)
                self.assertEqual(status["status"], "rollback_failed")
                self.assertFalse(status["rolled_back"])
                self.assertFalse(status["git_push_ok"])
                self.assertFalse(status["baseline_advanced"])
                self.assertTrue(status["retryable"])
                self.assertFalse((world["root"] / "pumeng-update-out" / "production" / "state" / "baseline.json").exists())
                self.assertEqual(final, foreign)
                self.assertEqual(local, world["head"])
                self.assertFalse(install["network_publisher"])
                self.assertEqual(injected["product_argv"][0], "git")
                self.assertNotIn("+", injected["product_argv"][-1])
                self.assertTrue(any(part.startswith("--force-with-lease=refs/heads/main:") for part in injected["product_argv"]))
                reports.append({
                    "window": window,
                    "status": status["status"],
                    "rolled_back": status["rolled_back"],
                    "git_push_ok": status["git_push_ok"],
                    "baseline_advanced": status["baseline_advanced"],
                    "network_publisher_after": install["network_publisher"],
                    "foreign": foreign,
                    "final_main": final,
                    "foreign_still_main": final == foreign,
                    "local_head": local,
                    "product_argv": injected["product_argv"],
                    "executed_argv": injected["executed_argv"],
                    "stderr": injected["stderr"],
                    "injection": injected["injection"],
                })
            out = Path("/tmp/rollback-cas-race.json")
            out.write_text(json.dumps({"label": "semantic-equivalent-observer", "windows": reports}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
