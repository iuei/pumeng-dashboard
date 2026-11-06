# 谱梦 · 进度监控

静态页读已发布的 `data.json`。公开站是 `https://iuei.github.io/pumeng-dashboard/`，只跟 `main` 走。这个功能分支没有获准发布，合并进 `main` 才会改公开站。

页面每 30 秒重新读取这份快照，不是业务源的实时同步。`updated_at` 和 `source_updated_at` 是快照里的原字段，含义没有在本仓库定义。

「去决策」和「标记已处理」只写在当前浏览器。那不等于工作完成，也没有写回业务源。本仓库里没有回写入口。

检查新快照用 `python3 scripts/check_update.py`。默认干跑。`--publish` 在这个入口里会拒绝。`python3 scripts/check_update.py --list-paths` 列出哪些拒绝是代码门、哪些生产控制还没有配置。

历史 `publish.sh` 的仓库内替换是 `scripts/replacement/publish.sh`。它不取令牌，也不推送。盒子上的旧脚本没有被这个替换改掉。说明在 `docs/REPLACEMENT.md`。

```bash
bash scripts/run_tests.sh
```

审计、决策和回滚步骤：

- `docs/AUDIT.md`
- `docs/DECISION_LEDGER.md`
- `docs/RELEASE_ROLLBACK.md`
