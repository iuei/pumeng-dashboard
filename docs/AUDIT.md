# 来源 / 回写审计 · PM-WEB-20261106-01

调查范围只在本仓库 `iuei/pumeng-dashboard` 和它的 GitHub Pages 配置。没有打开飞书、作品库、其他项目，也没有运行 `publish.sh` 或 Contents API。

## 已核实

| 事实 | 证据 |
|---|---|
| 全部提交里只有 `index.html`、`data.json`、`README.md`、`.nojekyll` | `git log --all --name-only`，五个提交 |
| 仓库里从未有 `tasks.json`、`build_data.py`、`publish.sh` | 同上 |
| 旧页面只 `fetch('data.json')`，每 30 秒再读一次，没有 POST/PUT | 改版前的 `index.html`（`5dad88f`） |
| `data.json` 带 `updated_at` 和 `source_updated_at` | 文件本身。`08:07` 那次两者差 1 分钟；`00:20` 那次两者相同 |
| 指标是写进 `data.json` 的数字，页面不算 | `metrics` 对象；旧页面直接显示这些字段 |
| 线上文件与 `origin/main` `5dad88f` 字节相同 | `data.json` sha256 `b65854f575e3bd5658d1af9e10ab31f38c5c567e2b7e906ac8dc9d75d4b1aa67`，`index.html` sha256 `42c198a6c8950e624ae53b70bae625780a696c524ebddde4b00ee6311daf188e`。GET `https://iuei.github.io/pumeng-dashboard/` 的两个文件与本地 main 一致 |
| Pages 从 `main` 的 `/` 发布，类型是 legacy | `GET /repos/iuei/pumeng-dashboard/pages`：`build_type=legacy`，`source.branch=main`，`source.path=/` |
| 唯一的 Actions 是 GitHub 自带的 `pages-build-deployment` | `actions/workflows` total_count=1，path=`dynamic/pages/pages-build-deployment`。仓库没有 `.github/workflows`（contents API 404，git 历史也没有） |
| 这 9 次运行全部是 `event=dynamic` 且 `head_branch=main` | `actions/runs?per_page=50` |
| 部署记录的 ref 全是 `main` | `deployments`、`pages/builds` |
| 允许部署到 `github-pages` 环境的分支只有 `main` 和 `gh-pages` | `environments/github-pages/deployment-branch-policies` |
| 远程只有 `main`，没有 `gh-pages` | `git ls-remote --heads origin`；`branches` API 返回 `["main"]` |
| 规则集是空的 | `rulesets` 返回 `[]` |
| 最近三次 bot 发布不在 9/12/15/18/21 | `pumeng-bot`：`2026-11-06 00:02`、`00:20`、`08:07` CST。人的两次 v2 提交在 `00:08` |

`updated_at` 和对应提交的钟点在同一分钟。这只说明字段随着那次提交出现。本仓库没有构建脚本，不能把这个字段证明成构建时间。

## 未核验

- Webhooks：`GET /hooks` 返回 403。不能写成“没有 webhook”。
- `main` 的分支保护：同样 403。
- `tasks.json` 是否存在于这台仓库外面。按任务边界没有去找。
- `build_data.py` / `publish.sh` 的真实行为。旧 README 只是提到它们，文件不在本仓库，本次没有执行。
- `source_updated_at` 是不是业务变更时间。仓库没有定义。
- 上游“冻结现有 routine”有没有生效。调查时 09:00 CST 这个槽没有新提交，但这同样符合“没变化”或“调度本来就不在 9 点跑”。历史发布钟点也不在这五个槽里。不能把冻结写成已证实。

## 线索，不是根因

旧 README 写过：静态页由 box 上的 `build_data.py` 生成 `data.json`，再经 `publish.sh` 推到 Pages。现 README 写：本地 `python3 build_data.py`，发布见上级 `publish.sh`，push 被拒时可用 Contents API。

这是文字线索。不能写成已经证实的 `tasks.json → 构建 → data.json → Pages`。本仓库能证实的后半段只是：`data.json` 被提交到 `main` 之后，Pages 会按 `main` 重新构建。

页面侧没有业务回写。所以「去决策 / 标记已处理」只写入这台浏览器的 `localStorage`，固定标明「仅本浏览器，未写回业务源，不等于工作完成」。正式回写入口：本仓库不存在，本次未调用。

## 代码门、模拟验证、生产控制

三者不要混写。

已实现的代码门只在 `scripts/check_update.py`：`--publish` 拒绝，审批绕过拒绝，`PUMENG_ALLOW_PRODUCTION_PUBLISH` 不打开发布，模拟发布必须绑定当前候选哈希，槽外的定时调用不生成候选。手动 `--trigger manual` 可以在槽外把变化留在本地候选里，但不能靠手动把 `--publish` 变成发布。

已模拟验证是本仓库测试调用上述入口，以及 `scripts/publish_paths.py` 在传入“请真正调用外部发布器”时仍不调用它。没有对 GitHub 发起真实的 push、merge、dispatch 或 Contents API 写入。

尚未配置的生产控制：规则集为 0；经典分支保护接口 403，不能当成已开启；Pages 仍从 `main` 构建，环境也允许 `gh-pages`。合并 PR 或推 `main` 仍会发布页面。动态 workflow 的手动触发没有在生产侧被我们关掉，也没有用真实 dispatch 去试。

未覆盖：`publish.sh` 不在仓库。Contents API 没有客户端，令牌能力未改、也未测。haole 的冻结回执明确只改了 routine 文字，没有改这些东西，也没有做手动绕过测试。所以 routine 文字不是硬门，不能写成手动路径已经不可绕过。

## 推送判断

`cursor/dashboard-update-gate-75bb` 不是 `main`，也不是 `gh-pages`。这次不新增 workflow。按上面的 Pages 源和分支策略，推这个分支、开一个不合并的 PR，不会更新 `https://iuei.github.io/pumeng-dashboard/`。

合并进 `main` 会更新线上页面，并触发 `pages-build-deployment`。本任务不合并、不部署。
