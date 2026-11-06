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


def plan_push(remote: str, branch: str) -> list:
    if branch != "main":
        raise ValueError("branch_not_main")
    if remote_has_credential(remote):
        raise ValueError("credential_in_remote")
    return ["git", "push", remote, "HEAD:main"]


class GitPagesPublisher:
    """Plans a credential-free git push and a separate Pages body check.

    `runner` and `fetch` are injected. The default runner refuses, so importing
    this class does not push or read a token.
    """

    uses_network = True

    def __init__(self, runner=None, fetch=None):
        self.runner = runner or subprocess_runner
        self.fetch = fetch or network_fetch

    def push_main(self, *, remote, branch, expected_semantic_sha):
        argv = plan_push(remote, branch)
        completed = self.runner(argv)
        ok = completed.get("returncode") == 0
        return {
            "ok": ok,
            "git_push_ok": ok,
            "pages_verified": False,
            "argv": argv,
            "remote_commit": completed.get("remote_commit"),
            "expected_semantic_sha": expected_semantic_sha,
        }

    def verify_pages(self, *, pages_data_url, expected_sha256):
        body = self.fetch(pages_data_url)
        import hashlib
        observed = hashlib.sha256(body).hexdigest() if isinstance(body, (bytes, bytearray)) else None
        ok = observed == expected_sha256
        return {"ok": ok, "git_push_ok": True, "pages_verified": ok, "observed_sha256": observed}


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
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return _result("concurrent_run", 3, retryable=True, **common)
    try:
        os.close(fd)
        pub = publisher if publisher is not None else RefusingPublisher()
        if isinstance(pub, RefusingPublisher):
            return _result("publisher_not_enabled", 5, **common)
        invoked = True
        network = bool(getattr(pub, "uses_network", False))
        pushed = pub.push_main(
            remote=install["remote"],
            branch="main",
            expected_semantic_sha=semantic,
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
            return _result(
                "pages_verify_failed",
                3,
                retryable=True,
                git_push_ok=True,
                pages_verified=False,
                called_network=network,
                publisher_invoked=invoked,
                remote_commit=pushed.get("remote_commit"),
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


def subprocess_runner(argv):
    import subprocess
    completed = subprocess.run(argv, check=False, capture_output=True)
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
