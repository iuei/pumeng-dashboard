"""Controlled production adapter. Default execution does not touch the network.

A release file is supplied by an operator after acceptance. This module never
writes one. Git push success and Pages verification are separate results.
The success baseline moves only after Pages verification succeeds.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pumeng_update import (
    is_beijing_slot,
    load_snapshot,
    read_state,
    semantic_sha256,
    sha256_json,
    summarize_diff,
)

REQUIRED_RELEASE = (
    "approval_id",
    "approver",
    "accepted_by",
    "approved_code_sha",
    "repo",
    "branch",
    "candidate_semantic_sha256",
    "summary_sha256",
)


def mint_release(*_args, **_kwargs):
    raise RuntimeError("release_must_come_from_outside")


def _load_json_object(path: Path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError:
        return None, "unreadable"
    except json.JSONDecodeError:
        return None, "JSONDecodeError"
    if not isinstance(data, dict):
        return None, "not_object"
    return data, None


def remote_has_credential(remote: str) -> bool:
    if not isinstance(remote, str) or "://" not in remote:
        return True
    rest = remote.split("://", 1)[1]
    return "@" in rest or "ghp_" in remote


def validate_install(install: dict):
    if not isinstance(install, dict) or install.get("installed") is not True:
        return "missing_install"
    if install.get("repo") != "iuei/pumeng-dashboard":
        return "install_repo_mismatch"
    if install.get("branch") != "main":
        return "install_branch_not_main"
    remote = install.get("remote")
    if not isinstance(remote, str) or remote_has_credential(remote):
        return "credential_in_remote"
    if not isinstance(install.get("pages_data_url"), str) or not install["pages_data_url"].startswith("https://"):
        return "missing_pages_url"
    if install.get("network_publisher") is True:
        return "ok"
    return "publisher_not_enabled"


def validate_release(release, *, semantic_sha: str, summary_sha: str, large: bool, running_sha: str, install: dict):
    if not isinstance(release, dict):
        return "missing_release"
    for key in REQUIRED_RELEASE:
        value = release.get(key)
        if not isinstance(value, str) or not value.strip():
            return "missing_release"
    if release["repo"] != install.get("repo") or release["branch"] != "main":
        return "release_target_mismatch"
    if release["approved_code_sha"] != running_sha:
        return "release_code_sha_mismatch"
    if release["candidate_semantic_sha256"] != semantic_sha or release["summary_sha256"] != summary_sha:
        return "stale_release"
    if large and release.get("large_change_confirmed") is not True:
        return "large_change_unconfirmed"
    return "ok"


class RefusingPublisher:
    """Used unless an install file explicitly enables the network publisher."""

    uses_network = False

    def push_main(self, **_kwargs):
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "stage": "refused_not_installed"}

    def verify_pages(self, **_kwargs):
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "stage": "refused_not_installed"}


def plan_push(remote: str, commit_sha: str, repo_dir) -> list:
    """Push one prepared commit from its own repository. Never pushes HEAD by name."""
    if not isinstance(commit_sha, str) or len(commit_sha) < 7:
        raise ValueError("missing_commit")
    if commit_sha == "HEAD":
        raise ValueError("refusing_head_shortcut")
    if remote_has_credential(remote) or ("github.com" in remote.lower() and os.environ.get("PUMENG_ALLOW_GITHUB_PUBLISH") != "1"):
        raise ValueError("remote_not_allowed")
    return ["git", "-C", str(repo_dir), "push", remote, f"{commit_sha}:refs/heads/main"]


class GitPagesPublisher:
    """Plans a credential-free git push and a separate Pages body check.

    `runner` and `fetch` are injected. The default runner refuses, so importing
    this class does not push or read a token.
    """

    uses_network = True

    def __init__(self, runner=None, fetch=None):
        self.runner = runner or subprocess_runner
        self.fetch = fetch or network_fetch

    def push_main(self, *, remote, branch, expected_semantic_sha, candidate_bytes=None, repo_dir=None, approved_code_sha=None):
        try:
            prepared = publish_prepared_commit(
                remote=remote,
                repo_dir=repo_dir or os.getcwd(),
                candidate_bytes=candidate_bytes,
                approved_code_sha=approved_code_sha,
                runner=self.runner,
            )
        except ValueError as exc:
            return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": exc.args[0] if exc.args else "ValueError"}
        prepared["expected_semantic_sha"] = expected_semantic_sha
        prepared["branch"] = branch
        self._before = prepared.get("remote_sha_before")
        self._remote = remote
        self._repo_dir = repo_dir or os.getcwd()
        return prepared

    def verify_pages(self, *, pages_data_url, expected_sha256):
        try:
            body = self.fetch(pages_data_url)
        except Exception:
            return {"ok": False, "git_push_ok": True, "pages_verified": False, "error_type": "pages_fetch_failed"}
        import hashlib
        observed = hashlib.sha256(body).hexdigest() if isinstance(body, (bytes, bytearray)) else None
        ok = observed == expected_sha256
        return {"ok": ok, "git_push_ok": True, "pages_verified": ok, "error_type": None if ok else "pages_hash_mismatch"}

    def rollback(self):
        before = getattr(self, "_before", None)
        remote = getattr(self, "_remote", None)
        if not before or not remote:
            return False
        argv = ["git", "-C", str(self._repo_dir), "push", remote, f"+{before}:refs/heads/main"]
        if "github.com" in remote.lower() and os.environ.get("PUMENG_ALLOW_GITHUB_PUBLISH") != "1":
            return False
        completed = self.runner(argv)
        return completed.get("returncode") == 0


def git_env():
    env = os.environ.copy()
    env.pop("GIT_DIR", None)
    env.pop("GIT_WORK_TREE", None)
    return env


def git_text(repo: Path, *args, input_bytes=None) -> tuple:
    import subprocess
    proc = subprocess.run(["git", "-C", str(repo), *args], input=input_bytes, capture_output=True, env=git_env())
    return proc.returncode, proc.stdout, proc.stderr


def remote_main_sha(remote: str) -> str | None:
    import subprocess
    if "github.com" in remote.lower() and os.environ.get("PUMENG_ALLOW_GITHUB_PUBLISH") != "1":
        raise ValueError("remote_not_allowed")
    proc = subprocess.run(["git", "ls-remote", remote, "refs/heads/main"], capture_output=True, env=git_env())
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.split()[0].decode("utf-8")


def publish_prepared_commit(*, remote, repo_dir, candidate_bytes, approved_code_sha, runner) -> dict:
    if not isinstance(candidate_bytes, (bytes, bytearray)):
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "candidate_bytes_missing"}
    code, head_out, _err = git_text(repo_dir, "rev-parse", "HEAD")
    if code != 0:
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "head_unreadable"}
    head = head_out.decode("utf-8").strip()
    if head != approved_code_sha:
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "head_mismatch", "head": head}
    before = remote_main_sha(remote)
    code, blob_out, _err = git_text(repo_dir, "hash-object", "-w", "--stdin", input_bytes=bytes(candidate_bytes))
    if code != 0:
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "blob_failed", "remote_sha_before": before}
    blob = blob_out.decode("utf-8").strip()
    code, tree_out, _err = git_text(repo_dir, "rev-parse", f"{head}^{{tree}}")
    if code != 0:
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "tree_unreadable", "remote_sha_before": before}
    parent_tree = tree_out.decode("utf-8").strip()
    listing = git_text(repo_dir, "ls-tree", parent_tree)[1]
    lines = []
    replaced = False
    for raw in listing.decode("utf-8").splitlines():
        if not raw.strip():
            continue
        meta, path = raw.split("\t", 1)
        mode, kind, sha = meta.split()
        if path == "data.json":
            lines.append(f"100644 blob {blob}\tdata.json")
            replaced = True
        else:
            lines.append(f"{mode} {kind} {sha}\t{path}")
    if not replaced:
        lines.append(f"100644 blob {blob}\tdata.json")
    code, new_tree_out, _err = git_text(repo_dir, "mktree", input_bytes="\n".join(lines).encode() + b"\n")
    if code != 0:
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "tree_failed", "remote_sha_before": before}
    new_tree = new_tree_out.decode("utf-8").strip()
    code, commit_out, _err = git_text(
        repo_dir,
        "-c", "user.email=publish@example.invalid",
        "-c", "user.name=pumeng-adapter",
        "commit-tree", new_tree, "-p", head, "-m", "publish candidate data.json",
    )
    if code != 0:
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "commit_failed", "remote_sha_before": before}
    commit = commit_out.decode("utf-8").strip()
    code, shown, _err = git_text(repo_dir, "cat-file", "-p", f"{commit}:data.json")
    if code != 0 or shown != bytes(candidate_bytes):
        return {"ok": False, "git_push_ok": False, "pages_verified": False, "error_type": "candidate_bytes_mismatch", "remote_sha_before": before}
    argv = plan_push(remote, commit, repo_dir)
    completed = runner(argv)
    after = remote_main_sha(remote)
    if completed.get("returncode") != 0 or after != commit:
        return {
            "ok": False,
            "git_push_ok": False,
            "pages_verified": False,
            "error_type": "push_failed",
            "remote_sha_before": before,
            "remote_sha_after": after,
            "prepared_commit": commit,
        }
    return {
        "ok": True,
        "git_push_ok": True,
        "pages_verified": False,
        "remote_commit": commit,
        "remote_sha_before": before,
        "remote_sha_after": after,
        "prepared_commit": commit,
    }


def advance_baseline(path: Path, payload: dict, replace=os.replace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if tmp.exists():
        tmp.unlink(missing_ok=True)


def _result(status: str, code: int, **extra) -> dict:
    body = {
        "baseline_advanced": False,
        "called_network": False,
        "exit_code": code,
        "git_push_ok": False,
        "pages_verified": False,
        "production_publish": False,
        "read_gh_token": False,
        "status": status,
    }
    body.update(extra)
    return body


def run_controlled_publish(
    *,
    baseline: dict,
    candidate: dict,
    trigger: str,
    now,
    install,
    release,
    running_sha: str,
    out_dir: Path,
    repo_dir=None,
    publisher=None,
    detect_only: bool = False,
    before_advance=None,
    replace=os.replace,
    candidate_bytes: bytes | None = None,
) -> dict:
    out_dir = Path(out_dir)
    summary = summarize_diff(baseline, candidate)
    semantic = semantic_sha256(candidate)
    summary_sha = sha256_json(summary)
    in_slot = is_beijing_slot(now)
    try:
        existing = read_state(out_dir)
    except Exception:
        return _result("invalid_state", 3, trigger=trigger)
    if existing and existing.get("pages_verified") is True and existing.get("semantic_sha256") == semantic:
        return _result("no_semantic_change", 0, already_current=True, trigger=trigger, candidate_semantic_sha256=semantic)
    common = {
        "candidate_semantic_sha256": semantic,
        "in_beijing_slot": in_slot,
        "large": summary["large"],
        "summary_sha256": summary_sha,
        "trigger": trigger,
    }
    if not summary["semantic_change"]:
        return _result("no_semantic_change", 0, **common)
    if trigger == "scheduled" and not in_slot:
        return _result("outside_slot", 0, would_change=True, **common)
    if trigger not in {"manual", "scheduled"}:
        return _result("bad_trigger", 2, **common)
    install_status = validate_install(install) if install is not None else "missing_install"
    if install_status == "publisher_not_enabled":
        return _result("publisher_not_enabled", 5, **common)
    if install_status != "ok":
        return _result(install_status, 4 if install_status != "missing_install" else 4, **common)
    release_status = validate_release(
        release,
        semantic_sha=semantic,
        summary_sha=summary_sha,
        large=summary["large"],
        running_sha=running_sha or "",
        install=install,
    )
    if release_status != "ok":
        return _result(release_status, 4, **common)
    if detect_only:
        return _result("detect_ready", 0, would_publish=True, publisher_called=False, **common)
    lock = out_dir / "state" / "publish.lock"
    acquired, blocked = acquire_publish_lock(lock)
    if blocked:
        return _result(blocked["status"], 3, retryable=True, lock_path=blocked.get("lock_path"), holder_pid=blocked.get("holder_pid"), **common)
    try:
        pub = publisher if publisher is not None else RefusingPublisher()
        if isinstance(pub, RefusingPublisher):
            return _result("publisher_not_enabled", 5, **common)
        invoked = True
        network = bool(getattr(pub, "uses_network", False))
        pushed = pub.push_main(
            remote=install["remote"],
            branch="main",
            expected_semantic_sha=semantic,
            candidate_bytes=candidate_bytes,
            repo_dir=str(repo_dir) if repo_dir else None,
            approved_code_sha=release.get("approved_code_sha"),
        )
        if not pushed.get("git_push_ok"):
            return _result(
                "push_failed",
                3,
                retryable=True,
                git_push_ok=False,
                pages_verified=False,
                called_network=network,
                publisher_invoked=invoked,
                **common,
            )
        import hashlib
        raw = candidate_bytes if candidate_bytes is not None else json.dumps(candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected_body_sha = hashlib.sha256(raw).hexdigest()
        verified = pub.verify_pages(pages_data_url=install["pages_data_url"], expected_sha256=expected_body_sha)
        if not verified.get("pages_verified"):
            rolled = False
            if hasattr(pub, "rollback"):
                try:
                    rolled = bool(pub.rollback())
                except Exception:
                    rolled = False
            return _result(
                "pages_verify_failed",
                3,
                retryable=True,
                git_push_ok=False if rolled else True,
                pages_verified=False,
                rolled_back=rolled,
                called_network=network,
                publisher_invoked=invoked,
                error_type=verified.get("error_type") or "pages_hash_mismatch",
                remote_sha_before=pushed.get("remote_sha_before"),
                **common,
            )
        state_path = out_dir / "state" / "baseline.json"
        payload = {
            "approval_id": release["approval_id"],
            "approved_code_sha": release["approved_code_sha"],
            "pages_verified": True,
            "remote_commit": pushed.get("remote_commit"),
            "semantic_sha256": semantic,
            "source": "production",
            "summary_sha256": summary_sha,
        }
        try:
            if before_advance is not None:
                before_advance()
            advance_baseline(state_path, payload, replace=replace)
        except Exception:
            return _result(
                "baseline_advance_failed",
                3,
                retryable=True,
                git_push_ok=True,
                pages_verified=True,
                baseline_advanced=False,
                called_network=network,
                publisher_invoked=True,
                **common,
            )
        return _result(
            "published",
            0,
            baseline_advanced=True,
            called_network=network,
            publisher_invoked=True,
            git_push_ok=True,
            pages_verified=True,
            production_publish=True,
            remote_commit=pushed.get("remote_commit"),
            **common,
        )
    finally:
        lock.unlink(missing_ok=True)


def pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def acquire_publish_lock(path: Path, ttl_seconds: int = 900):
    """Return (path, None) or (None, error). A live holder is never stolen."""
    import time
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if path.exists():
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            info = {}
        pid = info.get("pid") if isinstance(info, dict) else None
        started = info.get("started") if isinstance(info, dict) else None
        try:
            started = float(started) if started is not None else path.stat().st_mtime
            pid = int(pid) if pid is not None else 0
        except (TypeError, ValueError):
            started = path.stat().st_mtime
            pid = 0
        alive = pid_alive(pid) if pid else False
        age = now - started
        if alive:
            return None, {"status": "concurrent_run", "lock_path": str(path), "holder_pid": pid}
        if pid or age >= ttl_seconds:
            path.unlink(missing_ok=True)
        else:
            return None, {"status": "concurrent_run", "lock_path": str(path), "holder_pid": None}
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return None, {"status": "concurrent_run", "lock_path": str(path)}
    os.write(fd, json.dumps({"pid": os.getpid(), "started": now}).encode("utf-8"))
    os.close(fd)
    return path, None


def subprocess_runner(argv):
    import subprocess
    completed = subprocess.run(argv, check=False, capture_output=True, env=git_env())
    return {"returncode": completed.returncode, "remote_commit": None}


def network_fetch(url):
    import urllib.request
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read()


def select_publisher(install: dict):
    if isinstance(install, dict) and install.get("network_publisher") is True:
        return GitPagesPublisher()
    return RefusingPublisher()


def load_materials(install_path, release_path):
    install, install_error = (None, "missing_install") if not install_path else _load_json_object(install_path)
    release, release_error = (None, "missing_release") if not release_path else _load_json_object(release_path)
    return install, install_error, release, release_error


def state_sha(out_dir: Path):
    try:
        state = read_state(Path(out_dir))
    except Exception:
        return None
    if not state:
        return None
    return state.get("semantic_sha256")


def baseline_bytes(path: Path) -> bytes:
    file = Path(path)
    if not file.exists():
        return b""
    return file.read_bytes()
