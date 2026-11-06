# 发布入口替换

这是 PR 里的替换包，不是已经装到生产机器上的门。盒子上的 `publish.sh`、凭据、routine、仓库保护都不在本轮可改范围。拥有独立 main 权限的人仍然可以不经过这个包直接推送。

## 路径映射

| 既有外部路径 | PR 内替换 | 替换后做什么 |
|---|---|---|
| `build_data.py` | `scripts/replacement/build_snapshot.py` | 按同一 schema 从 tasks 对象生成候选。`pm_ids` 只留数量。命中通用敏感形态则整份拒绝 |
| `publish.sh` | `scripts/replacement/publish.sh` → `safe_publish.py` | 构建后进入 `scripts/check_update.py` 的同一判定。计划与手动共用。`--publish`、`--push`、`--contents-api` 都拒绝 |
| `gh auth token`、git push、Contents API、pages/builds | 无对应实现 | 替换包里没有这些调用 |
| `preview.sh` | `scripts/replacement/preview.sh` | 只写出候选。不启动服务，不发布 |

## 切换前必须成立

1. liu 对那一次真实发布另有批准。本卡没有这道批准。
2. haole 把外部 routine 改成调用本包，并停用盒子上的旧 `publish.sh`。本 PR 做不到这一步。
3. 用真实 `tasks.json` 在本地跑一遍敏感检测。历史脚本里的账号/标识正则已被脱敏成占位符，本包没有把占位符当成规则。通用规则挡不住那些未知字面量，所以这一步不能省。
4. 确认调用方不会再给旧脚本提供 `gh` 凭据。本包不读取 `GH_TOKEN` / `GITHUB_TOKEN`。

未满足 2 和 3 时，不能说生产发布路径已经换掉。

## 回滚（只写）

外部调度改回旧入口即可，因为旧脚本没有被这个 PR 删除。若要撤回本包，revert 引入 `scripts/replacement/` 的提交。不要为了回滚去推 `main` 或调用 Contents API。

## 命令

```bash
python3 scripts/replacement/safe_publish.py \
  --tasks /path/to/tasks.json \
  --baseline data.json \
  --trigger scheduled \
  --now "$(date --iso-8601=seconds)" \
  --out .pumeng-update-out
```

手动把 `--trigger` 换成 `manual`。模拟成功才推进 `--out/state/baseline.json`：

```bash
python3 scripts/replacement/safe_publish.py \
  --tasks /path/to/tasks.json \
  --baseline data.json \
  --trigger manual \
  --approval /path/to/approval.json \
  --simulate \
  --out .pumeng-update-out
```

不传 `--tasks` 时直接失败，不会去打开历史目录。
