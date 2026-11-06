"""Synthetic file:// rehearsals for two small increments.

The tasks, titles, and pages bodies in this file are fabricated for the test.
They are not the on-site tasks.json and they are not a business progress update.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLISH_ONCE = ROOT / "scripts" / "replacement" / "operator" / "publish-once.sh"
BIND = ROOT / "scripts" / "replacement" / "operator" / "bind-check.sh"
CST = timezone(timedelta(hours=8))
NOW = "2026-11-06T15:00:00+08:00"
WHEN = datetime(2026, 11, 6, 15, 0, tzinfo=CST)


def git_env():
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def run(argv, cwd=None, check=True):
    return subprocess.run(argv, cwd=cwd, check=check, capture_output=True, env=git_env())


def dumps(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def snapshot(tasks):
    from replacement.build_snapshot import build_snapshot
    built = build_snapshot(tasks, WHEN)
    built.pop("_scan", None)
    return built, dumps(built)


def base_tasks(title="合成甲"):
    return {
        "decisions": [],
        "lines": {
            "pumeng": {
                "doing": [{"id": "synthetic-a", "line": "pumeng", "note": "合成", "owner": "synth", "title": title}],
                "done_today": [],
                "paused": [],
                "todo": [],
            }
        },
        "metrics": {"feishu_base": None, "feishu_tables": None, "pm_ids": [], "songs_on_platform_approx": None},
        "timeline": [],
        "updated_at": "2026-11-06 15:00 Asia/Shanghai",
    }


class IncrementalPublishTests(unittest.TestCase):
    def setUp(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))

    def make_root(self, tmp: Path):
        root = tmp / "install"
        work = root / ".pages-repo"
        bare = tmp / "bare.git"
        pages = tmp / "pages-body.json"
        root.mkdir()
        work.mkdir()
        run(["git", "init", "-b", "main", str(work)])
        run(["git", "-C", str(work), "config", "user.email", "synth@example.invalid"])
        run(["git", "-C", str(work), "config", "user.name", "synth"])
        base, raw = snapshot(base_tasks())
        (work / "index.html").write_text("synthetic-ui\n", encoding="utf-8")
        (work / "dashboard.js").write_text("synthetic-js\n", encoding="utf-8")
        (work / "data.json").write_bytes(raw)
        run(["git", "-C", str(work), "add", "index.html", "dashboard.js", "data.json"])
        run(["git", "-C", str(work), "commit", "-m", "synthetic base"])
        head = run(["git", "-C", str(work), "rev-parse", "HEAD"]).stdout.decode().strip()
        run(["git", "init", "--bare", "-b", "main", str(bare)])
        run(["git", "-C", str(work), "push", str(bare), "HEAD:refs/heads/main"])
        remote = bare.resolve().as_uri()
        pages.write_bytes(raw)
        install = {
            "branch": "main",
            "installed": True,
            "network_publisher": False,
            "pages_data_url": pages.resolve().as_uri(),
            "remote": remote,
            "repo": "iuei/pumeng-dashboard",
            "work_tree": str(work.resolve()),
        }
        release = {
            "accepted_by": "haole",
            "approval_id": "synthetic-increment",
            "approved_code_sha": head,
            "approver": "liu",
            "branch": "main",
            "candidate_semantic_sha256": "pending",
            "large_change_confirmed": False,
            "named_code_sha": head,
            "repo": "iuei/pumeng-dashboard",
            "summary_sha256": "pending",
        }
        material = root / "pumeng-release"
        material.mkdir()
        (material / "install.json").write_text(json.dumps(install, indent=2) + "\n", encoding="utf-8")
        (material / "release.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
        (root / "tasks.json").write_text(json.dumps(base_tasks(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"bare": bare, "base": base, "head": head, "pages": pages, "remote": remote, "root": root, "work": work}

    def bind_release(self, world, tasks):
        from pumeng_update import semantic_sha256, sha256_json, summarize_diff
        built, raw = snapshot(tasks)
        baseline = json.loads((world["work"] / "data.json").read_text(encoding="utf-8"))
        summary = summarize_diff(baseline, built)
        path = world["root"] / "pumeng-release" / "release.json"
        release = json.loads(path.read_text(encoding="utf-8"))
        release["candidate_semantic_sha256"] = semantic_sha256(built)
        release["summary_sha256"] = sha256_json(summary)
        release["large_change_confirmed"] = False
        path.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        world["pages"].write_bytes(raw)
        (world["root"] / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return built, raw, summary

    def open_network(self, world, enabled):
        path = world["root"] / "pumeng-release" / "install.json"
        install = json.loads(path.read_text(encoding="utf-8"))
        install["network_publisher"] = enabled
        path.write_text(json.dumps(install, indent=2) + "\n", encoding="utf-8")

    def publish(self, world):
        env = git_env()
        env["PUMENG_ROOT"] = str(world["root"])
        env["PUMENG_CONFIRM_PUBLISH"] = "1"
        env["PUMENG_PUBLISH_NOW"] = NOW
        env.pop("PUMENG_ALLOW_GITHUB_PUBLISH", None)
        completed = subprocess.run(["bash", str(PUBLISH_ONCE)], capture_output=True, env=env, text=True)
        status_path = world["root"] / "pumeng-update-out" / "production" / "status.json"
        status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
        install = json.loads((world["root"] / "pumeng-release" / "install.json").read_text(encoding="utf-8"))
        return completed, status, install

    def remote_main(self, world):
        out = run(["git", "ls-remote", world["remote"], "refs/heads/main"]).stdout.decode().strip()
        return out.split()[0] if out else ""

    def test_two_small_increments_use_the_operator_entry(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_name:
            world = self.make_root(Path(tmp_name))
            self.bind_release(world, base_tasks("合成甲-增量一"))
            self.open_network(world, False)
            closed, status, install = self.publish(world)
            self.assertEqual(closed.returncode, 5)
            self.assertEqual(status.get("status"), "publisher_not_enabled")
            self.assertFalse(install["network_publisher"])
            self.assertEqual(self.remote_main(world), world["head"])

            self.open_network(world, True)
            first, status, install = self.publish(world)
            self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
            self.assertEqual(status["status"], "published")
            self.assertTrue(status["baseline_advanced"])
            self.assertFalse(install["network_publisher"])
            tip1 = self.remote_main(world)
            local1 = run(["git", "-C", str(world["work"]), "rev-parse", "HEAD"]).stdout.decode().strip()
            parent1 = run(["git", "-C", str(world["work"]), "rev-parse", "HEAD^"]).stdout.decode().strip()
            self.assertEqual(local1, tip1)
            self.assertEqual(parent1, world["head"])
            self.assertEqual((world["work"] / "data.json").read_bytes(), world["pages"].read_bytes())
            bind = subprocess.run(["bash", str(BIND), str(world["work"])], capture_output=True, text=True, env={**git_env(), "PUMENG_ROOT": str(world["root"])})
            self.assertEqual(bind.returncode, 0, bind.stdout + bind.stderr)
            self.assertIn("bind_status=ready", bind.stdout)
            self.assertIn(f"head={tip1}", bind.stdout)
            self.assertNotIn("unexpected_head", bind.stdout)

            self.bind_release(world, base_tasks("合成甲-增量二"))
            self.open_network(world, True)
            second, status, install = self.publish(world)
            self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
            self.assertEqual(status["status"], "published")
            self.assertFalse(install["network_publisher"])
            tip2 = self.remote_main(world)
            local2 = run(["git", "-C", str(world["work"]), "rev-parse", "HEAD"]).stdout.decode().strip()
            parent2 = run(["git", "-C", str(world["work"]), "rev-parse", "HEAD^"]).stdout.decode().strip()
            self.assertEqual(local2, tip2)
            self.assertEqual(parent2, tip1)
            state = json.loads((world["root"] / "pumeng-update-out" / "production" / "state" / "baseline.json").read_text(encoding="utf-8"))
            self.assertEqual(state["semantic_sha256"], status["candidate_semantic_sha256"])
            self.assertEqual(state["approved_code_sha"], world["head"])
            shown = run(["git", "--git-dir", str(world["bare"]), "show", "main:data.json"]).stdout
            self.assertEqual(shown, (world["work"] / "data.json").read_bytes())
            self.assertIn("合成甲-增量二".encode(), shown)
            refspec_commit = tip2
            self.assertFalse(refspec_commit.startswith("+"))

    def test_stale_release_and_large_change_do_not_push(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_name:
            world = self.make_root(Path(tmp_name))
            self.bind_release(world, base_tasks("合成甲-增量一"))
            release_path = world["root"] / "pumeng-release" / "release.json"
            release = json.loads(release_path.read_text(encoding="utf-8"))
            release["summary_sha256"] = "0" * 64
            release_path.write_text(json.dumps(release) + "\n", encoding="utf-8")
            self.open_network(world, True)
            stale, status, _install = self.publish(world)
            self.assertEqual(stale.returncode, 4)
            self.assertEqual(status["status"], "stale_release")
            self.assertEqual(self.remote_main(world), world["head"])

            tasks = base_tasks("合成甲")
            tasks["lines"]["pumeng"]["doing"] = [
                {"id": f"synthetic-{i}", "line": "pumeng", "owner": "synth", "title": f"合成{i}"} for i in range(3)
            ]
            self.bind_release(world, tasks)
            self.open_network(world, True)
            large, status, _install = self.publish(world)
            self.assertEqual(large.returncode, 4, large.stdout + large.stderr)
            self.assertEqual(status["status"], "large_change_unconfirmed")
            self.assertEqual(self.remote_main(world), world["head"])

    def test_dirty_tree_pages_mismatch_and_rejected_push_leave_baseline(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_name:
            world = self.make_root(Path(tmp_name))
            self.bind_release(world, base_tasks("合成甲-增量一"))
            (world["work"] / "untracked-synthetic.txt").write_text("dirty\n", encoding="utf-8")
            self.open_network(world, True)
            dirty, _status, _install = self.publish(world)
            self.assertEqual(dirty.returncode, 5, dirty.stdout + dirty.stderr)
            self.assertIn("dirty_work_tree", dirty.stdout)
            self.assertEqual(self.remote_main(world), world["head"])
            (world["work"] / "untracked-synthetic.txt").unlink()

            world["pages"].write_bytes(b'{"synthetic":"mismatch"}\n')
            self.open_network(world, True)
            mismatched, status, _install = self.publish(world)
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertIn(status["status"], {"pages_verify_failed", "rollback_failed"})
            self.assertFalse(status.get("baseline_advanced", False))
            self.assertEqual(self.remote_main(world), world["head"])
            self.assertEqual(run(["git", "-C", str(world["work"]), "rev-parse", "HEAD"]).stdout.decode().strip(), world["head"])

            hook = world["bare"] / "hooks" / "update"
            hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            hook.chmod(0o755)
            self.bind_release(world, base_tasks("合成甲-增量一"))
            self.open_network(world, True)
            rejected, status, _install = self.publish(world)
            self.assertEqual(rejected.returncode, 3, rejected.stdout + rejected.stderr)
            self.assertEqual(status["status"], "push_failed")
            self.assertTrue(status["retryable"])
            self.assertFalse(status["baseline_advanced"])
            self.assertEqual(self.remote_main(world), world["head"])

    def test_concurrent_data_tip_is_parent_and_foreign_tip_is_not_rewound(self):
        import tempfile
        from replacement.production_adapter import GitPagesPublisher
        with tempfile.TemporaryDirectory() as tmp_name:
            world = self.make_root(Path(tmp_name))
            self.bind_release(world, base_tasks("合成甲-增量一"))
            self.open_network(world, True)
            first, status, _install = self.publish(world)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            tip1 = self.remote_main(world)
            other = Path(tmp_name) / "other"
            run(["git", "clone", world["remote"], str(other)])
            run(["git", "-C", str(other), "config", "user.email", "synth@example.invalid"])
            run(["git", "-C", str(other), "config", "user.name", "synth"])
            payload = json.loads((other / "data.json").read_text(encoding="utf-8"))
            payload["decisions"] = [{"id": "synthetic-side", "note": "并发", "owner": "synth", "title": "合成并发"}]
            (other / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            run(["git", "-C", str(other), "add", "data.json"])
            run(["git", "-C", str(other), "commit", "-m", "synthetic concurrent data"])
            run(["git", "-C", str(other), "push", "origin", "HEAD:refs/heads/main"])
            side = run(["git", "-C", str(other), "rev-parse", "HEAD"]).stdout.decode().strip()
            self.bind_release(world, base_tasks("合成甲-增量二"))
            self.open_network(world, True)
            second, status, _install = self.publish(world)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            tip2 = self.remote_main(world)
            parent = run(["git", "--git-dir", str(world["bare"]), "rev-parse", "main^"]).stdout.decode().strip()
            self.assertEqual(parent, side)
            self.assertNotEqual(tip2, side)
            ancestor = run(["git", "--git-dir", str(world["bare"]), "merge-base", "--is-ancestor", side, tip2], check=False)
            self.assertEqual(ancestor.returncode, 0)
            self.assertEqual(run(["git", "-C", str(world["work"]), "rev-parse", "HEAD"]).stdout.decode().strip(), tip2)

            publisher = GitPagesPublisher()
            publisher._pushed = True
            publisher._pushed_commit = tip1
            publisher._before = world["head"]
            publisher._remote = world["remote"]
            publisher._repo_dir = str(world["work"])
            self.assertFalse(publisher.rollback())
            self.assertEqual(self.remote_main(world), tip2)

    def test_unapproved_tree_is_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_name:
            world = self.make_root(Path(tmp_name))
            other = Path(tmp_name) / "other"
            run(["git", "clone", world["remote"], str(other)])
            run(["git", "-C", str(other), "config", "user.email", "synth@example.invalid"])
            run(["git", "-C", str(other), "config", "user.name", "synth"])
            (other / "index.html").write_text("synthetic-ui-changed\n", encoding="utf-8")
            run(["git", "-C", str(other), "add", "index.html"])
            run(["git", "-C", str(other), "commit", "-m", "synthetic ui change"])
            run(["git", "-C", str(other), "push", "origin", "HEAD:refs/heads/main"])
            foreign = self.remote_main(world)
            self.bind_release(world, base_tasks("合成甲-增量一"))
            self.open_network(world, True)
            rejected, status, _install = self.publish(world)
            self.assertEqual(rejected.returncode, 3, rejected.stdout + rejected.stderr)
            self.assertEqual(status.get("error_type"), "unapproved_remote")
            self.assertEqual(self.remote_main(world), foreign)
            self.assertEqual(run(["git", "-C", str(world["work"]), "rev-parse", "HEAD"]).stdout.decode().strip(), world["head"])

    def test_old_publish_rename_is_reversible_inside_a_temp_root(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp_name:
            root = Path(tmp_name) / "install"
            root.mkdir()
            script = root / "publish.sh"
            script.write_text("#!/bin/sh\necho synthetic-old\n", encoding="utf-8")
            env = git_env()
            env["PUMENG_ROOT"] = str(root)
            disabled = subprocess.run(["bash", str(ROOT / "scripts/replacement/operator/disable-old-publish.sh")], capture_output=True, text=True, env=env)
            self.assertEqual(disabled.returncode, 0, disabled.stderr)
            self.assertFalse(script.exists())
            self.assertTrue((root / "publish.sh.disabled-20261106").exists())
            restored = subprocess.run(["bash", str(ROOT / "scripts/replacement/operator/restore-old-publish.sh")], capture_output=True, text=True, env=env)
            self.assertEqual(restored.returncode, 0, restored.stderr)
            self.assertEqual(script.read_text(encoding="utf-8"), "#!/bin/sh\necho synthetic-old\n")

    def test_shipped_ui_bytes_match_main(self):
        import hashlib
        for name in ("index.html", "dashboard.js"):
            committed = run(["git", "show", f"origin/main:{name}"]).stdout
            current = (ROOT / name).read_bytes()
            self.assertEqual(hashlib.sha256(committed).hexdigest(), hashlib.sha256(current).hexdigest())
