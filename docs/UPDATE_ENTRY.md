# 标准检查入口

外部调度和人手动更新用同一个脚本：`scripts/check_update.py`。默认 `--trigger scheduled`，默认干跑。脚本不连网、不调用 git、不写 `data.json`。生产发布没有实现；`--publish` 和 `PUMENG_ALLOW_PRODUCTION_PUBLISH` 都会被拒绝，而且不会把环境变量的值写进日志。

本仓库不新增 cron、GitHub `schedule`、常驻发布定时器。北京时间 9/12/15/18/21 点的调用仍由现有外部调度负责。页面上原来的 30 秒只是重新读取已发布的 `data.json`，不是这条检查入口。

## 命令

定时检查（槽外只记录，不生成候选）：

```bash
python3 scripts/check_update.py \
  --baseline data.json \
  --candidate /path/to/new-snapshot.json \
  --trigger scheduled \
  --out .pumeng-update-out
```

手动检查（不看钟点，判断规则相同）：

```bash
python3 scripts/check_update.py \
  --baseline data.json \
  --candidate /path/to/new-snapshot.json \
  --trigger manual \
  --out .pumeng-update-out
```

`--now` 只用于测试注入带时区的时间，不能代替批准。不带时区的时间直接失败。

## 槽

Asia/Shanghai 的 9、12、15、18、21 点，整点小时都算在槽内（09:00–09:59）。08:07、00:20 不算。UTC 会先换算到上海。

## 语义差异

只忽略快照**顶层**的这些键：

`updated_at`、`source_updated_at`、`generated_at`、`build_time`、`built_at`、`fetched_at`、`checked_at`、`snapshot_written_at`、`refresh_seconds`

嵌套的同名字段照算变化。`blocker`、状态、标题、指标、时间线正文都不在忽略集合里。不认识的新字段也算变化，避免把未知噪声静默吃掉。

有实质变化才在 `--out/candidates/<语义哈希>/` 写下快照、摘要和 manifest。只有时间戳变化时退出 0，状态 `no_semantic_change`，不写候选。

## 批准

批准绑定**这一份**候选的两个哈希，不能拿上一份候选的批准来用。时钟不是过期条件；哈希不一致就是陈旧批准。

```json
{
  "candidate_semantic_sha256": "<status.json 里的值>",
  "summary_sha256": "<status.json 里的值>",
  "approver": "liu",
  "approved_at": "2026-11-06T12:00:00+08:00",
  "large_change_confirmed": false
}
```

大改必须同一份批准里 `large_change_confirmed` 为 JSON `true`。大改的定义（本入口自己的门，不是业务制度）：

- `metrics` 下有任何变化，或
- 新增加删除的 id/date 达到 3 个，或
- 字段变化路径达到 8 条

定时和手动都走 `execute()`。没有跳过审批的成功路径。`--bypass-approval` 和已设置的 `PUMENG_SKIP_APPROVAL` 直接拒绝。

## 模拟发布

```bash
python3 scripts/check_update.py \
  --baseline data.json \
  --candidate /path/to/new-snapshot.json \
  --trigger manual \
  --approval /path/to/approval.json \
  --simulate \
  --out .pumeng-update-out
```

成功时只在 `--out/simulated/<哈希>/` 写收据，并把 `--out/state/baseline.json` 的语义哈希推进到这份候选。收据写明 `production: false`。失败、槽外、干跑、坏 JSON 都不改这个哈希。坏 JSON 会留下 `--out/retry/last_failure.json`，里面只有错误类型，没有文件正文。

同一份候选再模拟一次不会把基线再推进。基线文件损坏时拒绝覆盖。

## 退出码

| 码 | 状态 |
|---|---|
| 0 | `no_semantic_change`、`candidate_ready`、`outside_slot`、`seeded`、`baseline_exists`、`simulated` |
| 2 | 缺候选、触发器不对、时间没有时区、种子和检查写在同一次 |
| 3 | 基线/候选/批准/成功基线文件损坏，可重试 |
| 4 | 缺批准、陈旧批准、大改未确认 |
| 5 | 试图跳过审批，或试图生产发布 |

标准输出是一份 JSON 结果。每次运行另外写 `--out/status.json` 和 `--out/logs/`。
