# PLAN · PM-WEB-20261106-01

写入时间：2026-11-06 11:15 左右（Asia/Shanghai）。10:30 的首报时点已过。这是首次落盘的可核验计划，不回溯成 10:30 已交付，也不把本轮自测写成独立验收或上线。

## 基线

- 线上 / `origin/main`：`5dad88fd079d33fef8b222327ec43cfc466d2161`
- 功能分支当前提交：`873c1cee2de90fc8ecc80b5bc27f5e1474be998f`（`cursor/dashboard-update-gate-75bb`）
- `data.json` sha256：`b65854f575e3bd5658d1af9e10ab31f38c5c567e2b7e906ac8dc9d75d4b1aa67`（与线上一致，本分支不改它）

## 真实链路

已核实后半段：提交进 `main` 的 `data.json` / 页面 → GitHub Pages legacy，源分支 `main` 路径 `/` → 自带 workflow `pages-build-deployment`（`event=dynamic`，历史运行都在 `main`）→ https://iuei.github.io/pumeng-dashboard/ 。`github-pages` 环境还允许名为 `gh-pages` 的分支，远程目前没有该分支。规则集数量为 0。

未在本仓库出现、因此不是已证实前半段：`tasks.json`、`build_data.py`、上级 `publish.sh`、Contents API。Webhooks 与经典分支保护接口为 403。

haole 的冻结回执只说明 routine 文字已改成：北京时间 9/12/15/18/21 前后 15 分钟做只读比较，禁止真实发布/推送/合并/部署，普通待发布变化静默保留。同一回执写明没有改 `publish.sh`、CLI 权限、workflow、仓库保护，也没有做手动入口绕过测试。这份文字不是代码硬门，也不能当成手动路径已不可绕过的证据。

## 关键风险

- 推 `main`、合并 PR、或新建并推送 `gh-pages`，仍会走到 Pages。本仓库没有服务端保护能挡住。
- `publish.sh` 与 Contents API 不在本仓库，行为未覆盖。
- `workflow_dispatch` 能否从网页触发，动态 workflow 的 YAML 不在仓库里，不能把“历史只有 main”写成“手动触发已被禁止”。
- 本分支里的 `--publish` 拒绝只约束 `scripts/check_update.py`。它不约束仓库外的脚本和 GitHub 按钮。
- 手动 `--trigger manual` 仍可在槽外生成待发布候选（本地保留）。这不是发布，也不能被 routine 文字自动关掉。

## 本轮要做完的事

- 把槽从“整点小时”改成目标钟点前后 15 分钟，只用于定时检查分类。
- 把已发现的发布路径写成代码可打印的分类：已实现代码门、要用 mock 验证的拒绝、尚未配置的生产控制、仓库外未覆盖脚本。
- 用隔离调用验证手动入口和 `--publish` / 审批绕过 / 环境变量不能打开发布；不向 GitHub 做真实发布试探。
- 推送前再核对 workflow。只更新功能分支和已有 PR。不合并、不部署。

## 预估

本轮内完成上述代码和 mock 自测。做不到的是：给 GitHub 配生产门，或验证仓库外的 `publish.sh`。独立验收不在本轮。

## 本轮结果

代码和隔离测试已做完，没有配置生产控制，没有真实发布。

- 槽已改为目标钟点前后 15 分钟。`--publish` 在槽内仍然拒绝。
- `python3 scripts/check_update.py --list-paths` 会打印路径分类，并带 `production_control_configured: false`。
- 自测：`bash scripts/run_tests.sh` 结束码 0。Python 20 项 OK，Node 10 项 OK，浏览器 `BROWSER_OK`。日志在同目录的 `test-python.log`、`test-node.log`、`test-browser.log`。
- 推送前复核：workflow 仍只有 `dynamic/pages/pages-build-deployment`；最近一次运行仍是 `main` 上的 `5dad88f`（2026-11-06 00:08 UTC）。远程 `main` 没有新提交。

