# 交接线索逐项核实

范围只在本仓库 `iuei/pumeng-dashboard` 的 git 历史、GitHub API，以及公开站的一次 GET。没有打开 `tasks.json`、`site/data.json`、`.pages-repo`、作品库，没有读 `publish.sh` / `build_data.py` 的实现，没有写 main，没有做 Contents API 写入。

核对时间：2026-11-06，功能分支 `cf395dc` 已在远程，PR #1 已打开。下表是这次核对的结果。

| 线索 | 结果 | 证据 |
|---|---|---|
| 公开站是 `main` 上的静态 Pages | 已核实 | Pages `build_type=legacy`，`source.branch=main`，`source.path=/`。最新构建 commit `5dad88f`，时间 `2026-11-06T00:08:00Z`，pusher `iuei` |
| 线上文件仍是该提交 | 已核实 | 公开站 `data.json` 与本仓库 `data.json` sha256 都是 `b65854f575e3bd5658d1af9e10ab31f38c5c567e2b7e906ac8dc9d75d4b1aa67`。`updated_at` 为 `2026-11-06 08:07 Asia/Shanghai` |
| 提交落到 `main` 之后出现 Pages 部署 | 已核实到历史样本 | 6 条 deployment 的 `ref` 都是 `main`，sha 为 `5dad88f`、`04abef8`、`0bc00cf`、`9b3f13b`。对应提交作者是 `pumeng-bot` 或 `iuei`。这只证明提交在 main 上之后发生了构建 |
| push 与 Contents API 哪一个把文件写上 main | 未核实 | 两种写法都会变成 main 上的提交。现有提交看不出用的是哪一种。没有执行 Contents API 写入，也没有读发布脚本 |
| `publish.sh` 仍能发布，且权限未收回 | 未核实 | 脚本不在本仓库任何提交里。`gh` 所用集成令牌对仓库的 permissions 全是 false。git 凭据曾经推成功能分支，没有用它试推 main，因此不能判断发布凭据是否还在 |
| `tasks.json` → `build_data.py` → `site/data.json` | 未核实，不当作根因 | 这三个路径不在本仓库历史中。本次按交接边界没有打开它们 |
| 构建脚本不调用飞书/腾讯 | 只核实了本仓库页面 | 本仓库页面和检查脚本没有这类客户端。构建脚本本身没有读，不能给它下结论 |
| 页面约 30 秒刷新只是重读 `data.json` | 已核实 | `5dad88f` 的 `index.html` 是 `fetch('data.json?ts=')` 加 30 秒 `setInterval`。当前 `dashboard.js` 的 `REFRESH_MS` 仍是 30000，没有 POST |
| 指标是快照里的预填数字 | 已核实到本仓库快照 | `songs_on_platform_approx` 为 4700。页面不重算。数字当初是否从别处抄入，未核实 |
| 时间线 10-31 到 11-04 为空数组 | 已核实到本仓库快照 | 空的日期是 2026-10-31、11-01、11-02、11-03、11-04。11-05 和 11-06 有条目。空数组不是“当天没有业务”的证明 |
| 谁在改源文件、有没有别的调度 | 未核实 | 本仓库看不到写入器。管理侧冻结文字没有附带 routine 配置正文 |
| 非 main 推送会不会部署 | 按当前设置，已发生的两次功能分支推送没有部署 | 分支 `cursor/dashboard-update-gate-75bb` 的 Actions `total_count=0`。`2026-11-06T02:00:00Z` 之后的运行数为 0。事件计数：`dynamic` 9，`push` 0，`pull_request` 0，`pull_request_target` 0，`workflow_dispatch` 0，`workflow_run` 0，`schedule` 0。这 9 次里能看到的最新一次仍是 main/`5dad88f` |
| 打开或更新 PR 会不会部署 | 已发生的 PR #1 没有部署 | PR 检查列表为空。`873c1ce` 与 `cf395dc` 的 check-runs 都是 0。Pages 最新构建仍是 `5dad88f` |
| 仓库里有没有别的 workflow | 已核实没有文件型 workflow | `main` 上 `.github` 为 404。功能分支树里没有 workflow、`publish.sh`、`tasks.json`。唯一 workflow 是动态的 `pages-build-deployment`，state `active`。它的 YAML 不在仓库里，所以不能引用它的 `on:` 原文 |
| `gh-pages` 分支 | 未做创建试验 | 部署分支策略里有这个名字，远程 heads 只有 `main` 和功能分支。Pages 源目前写的是 `main`。没有新建 `gh-pages` |
| 分支保护、webhook | 未知 | 两个接口都是 403。规则集长度为 0，这只说明没有 ruleset，不能代替 403 的那两项 |
| routine 冻结文字 | 不是本仓库的门 | 没有读到 routine 配置。代码入口的拒绝只覆盖 `scripts/check_update.py` |

因此：在当前仓库设置下，继续推这个功能分支或更新已有 PR，没有观察到会发布 Pages。推 `main`、合并进 `main`、以及对 main 的 Contents API 写入，会落到 Pages 正在构建的那个分支上；后一条没有亲自写过，只是从“Pages 构建 main 尖端”推出来的，不能写成已经试过的发布路径。`publish.sh` 是否仍能调用，仍是缺口。

## 缺口②（安装之后才能验，本轮不关闭）

旧入口是否已停用、替换包是否已装进运行目录、凭据是否收回、仓库保护是否还有本令牌看不见的规则，都不能靠这次代码修改判过。安装和切换步骤写在 `docs/INSTALL-CHECKLIST.md`，等 haole 点名 SHA 之后才执行。本轮没有安装，也没有改运行目录。
