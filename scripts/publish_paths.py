"""Classify publish paths.

Code gates exist only inside this repository's check entry. A management
note that a routine was frozen is not a gate. This module never spawns
git, never calls GitHub, and never runs publish.sh.
"""

from __future__ import annotations

PATHS = (
    {
        "id": "manual_publish_flag",
        "coverage": "in_repo",
        "code_gate": "implemented",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "scripts/check_update.py --trigger manual --publish 在入口内拒绝。GitHub 侧没有因此上锁。",
    },
    {
        "id": "scheduled_publish_flag",
        "coverage": "in_repo",
        "code_gate": "implemented",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "定时触发带 --publish 同样拒绝，包括落在 9/12/15/18/21 前后 15 分钟内。",
    },
    {
        "id": "bypass_approval",
        "coverage": "in_repo",
        "code_gate": "implemented",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "--bypass-approval 与已设置的 PUMENG_SKIP_APPROVAL 都会被拒绝。",
    },
    {
        "id": "allow_production_env",
        "coverage": "in_repo",
        "code_gate": "implemented",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "PUMENG_ALLOW_PRODUCTION_PUBLISH 不会打开发布，入口里没有发布实现。",
    },
    {
        "id": "simulate_without_approval",
        "coverage": "in_repo",
        "code_gate": "implemented",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "有实质变化时，手动或定时的 --simulate 都要当前候选的批准。",
    },
    {
        "id": "stale_or_large_approval",
        "coverage": "in_repo",
        "code_gate": "implemented",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "哈希不一致或大改未确认时不推进成功基线。",
    },
    {
        "id": "forged_now",
        "coverage": "in_repo",
        "code_gate": "slot_only",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "--now 只能改变槽分类。它不能批准，也不能打开发布。",
    },
    {
        "id": "git_push_main",
        "coverage": "github",
        "code_gate": "not_applicable",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "Pages 源是 main。规则集为 0。经典分支保护接口 403，不能当成已上锁。本入口不执行 push。",
    },
    {
        "id": "git_push_gh_pages",
        "coverage": "github",
        "code_gate": "not_applicable",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "github-pages 环境允许 gh-pages。远程目前没有该分支。本入口不会创建它。",
    },
    {
        "id": "pull_request_merge",
        "coverage": "github",
        "code_gate": "not_applicable",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "把功能分支合并进 main 会发布页面。没有规则集挡住合并按钮。",
    },
    {
        "id": "workflow_dispatch_pages",
        "coverage": "github",
        "code_gate": "not_applicable",
        "production_control": "unknown",
        "routine_text_is_gate": False,
        "reason": "pages-build-deployment 是动态 workflow，YAML 不在仓库。历史运行都在 main，不能证明网页手动触发已被禁止。本次不用真实 dispatch 去试。",
    },
    {
        "id": "contents_api",
        "coverage": "uncovered_external",
        "code_gate": "absent",
        "production_control": "unknown",
        "routine_text_is_gate": False,
        "reason": "README 历史提到 Contents API。本仓库没有这个客户端，也没有改过令牌权限。",
    },
    {
        "id": "publish_sh",
        "coverage": "uncovered_external",
        "code_gate": "absent",
        "production_control": "unknown",
        "routine_text_is_gate": False,
        "reason": "publish.sh 不在本仓库。冻结回执写明没有改它。不能声称它已停止发布。",
    },
    {
        "id": "routine_text_freeze",
        "coverage": "management_receipt",
        "code_gate": "absent",
        "production_control": "absent",
        "routine_text_is_gate": False,
        "reason": "haole 只改了 routine 文字，未改脚本、权限、workflow、仓库保护，也未做手动绕过测试。文字不是硬门。",
    },
)


def list_paths():
    return [dict(item) for item in PATHS]


def attempt(path_id, *, routine_freeze_text=False, invoke_external=False, publisher=None):
    """Classify one path. `publisher` is never called. External tools are not started."""
    spec = next((item for item in PATHS if item["id"] == path_id), None)
    if spec is None:
        raise KeyError(path_id)
    if publisher is not None:
        # Present so tests can prove a bypass attempt does not call out.
        pass
    return {
        "id": spec["id"],
        "coverage": spec["coverage"],
        "code_gate": spec["code_gate"],
        "production_control": spec["production_control"],
        "routine_text_is_gate": False,
        "routine_freeze_text_seen": bool(routine_freeze_text),
        "invoke_external_honored": False,
        "publisher_called": False,
        "called_network": False,
        "covered": spec["coverage"] == "in_repo" and spec["code_gate"] == "implemented",
        "reason": spec["reason"],
        "ignored_request": bool(routine_freeze_text or invoke_external),
    }
