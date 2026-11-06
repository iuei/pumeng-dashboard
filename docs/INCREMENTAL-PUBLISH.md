# 连续小增量发布

这份包的代码锚是打包时写进 `MANIFEST.json` 的 `source_commit`，也就是 `code_anchor`。安装时 `release.json` 的 `approved_code_sha` 和 `named_code_sha` 都写这个锚。程序不会自己把某个 SHA 写成已批准。更早的 `c4b48e8d07dc4fc8d2ce91929713bca67ad1e045` 只是上一轮界面提交，不是这份包的锚，也不能抄进新的 release。

页面仓库的 HEAD 可以是这个锚，也可以是它的只改 `data.json` 的后裔。其它文件一旦不同，绑定和发布都拒绝。

每次发布使用新的 `candidate_semantic_sha256` 和 `summary_sha256`。`network_publisher=false` 与 `stale_release` 仍是关门。大改仍要 `large_change_confirmed=true`，程序不会自动填上。

正常推送不带 `+`。远端 tip 必须是获批代码的数据后裔；本机干净时才快进到这个 tip，再在它上面准备下一次提交。Pages 字节一致之后，本机 HEAD、`data.json` 和成功基线一起继承该提交。推送被拒、远端不是数据后裔、Pages 不符或断开、工作区脏、本机继承失败时，成功基线不前进。Pages 失败时的回滚只在远端 tip 仍是这次推上去的提交时进行，不会强行覆盖别人后来的 tip。

## 安装

把本仓库的 `scripts/` 拷到安装根的 `scripts/`。默认安装根是 `/workspace/music-biz/dashboard`，演练时设置 `PUMENG_ROOT`。不要把脚本放进 `.pages-repo`。

```bash
export PUMENG_ROOT=/path/to/install-root
cp -a scripts/. "$PUMENG_ROOT/scripts/"
mkdir -p "$PUMENG_ROOT/pumeng-release" "$PUMENG_ROOT/pumeng-update-out" "$PUMENG_ROOT/.pages-repo"
```

`install.json` 的 `work_tree` 必须等于 `$PUMENG_ROOT/.pages-repo`。`remote` 不写用户信息或 token。`network_publisher` 保持 false。指向 github.com 的远端还要在那一次命令上设置 `PUMENG_ALLOW_GITHUB_PUBLISH=1`。隔离演练可以用 `file://` 远端和 `file://` 的页面正文。

## 验证

```bash
export PUMENG_ROOT=/path/to/install-root
export PUMENG_PUBLISH_NOW='2026-11-06T15:00:00+08:00'
python3 "$PUMENG_ROOT/scripts/replacement/safe_publish.py" \
  --tasks "$PUMENG_ROOT/tasks.json" \
  --baseline "$PUMENG_ROOT/.pages-repo/data.json" \
  --trigger manual \
  --now "$PUMENG_PUBLISH_NOW" \
  --out "$PUMENG_ROOT/pumeng-update-out/dry-run"
bash "$PUMENG_ROOT/scripts/replacement/operator/bind-check.sh"
```

把干跑状态里的 `candidate_semantic_sha256` 和 `summary_sha256` 写入 `release.json`。`large` 为 true 时才把 `large_change_confirmed` 设为 true。无变化时状态是 `no_semantic_change`，不要开门。

## 一次发布

先把 `network_publisher` 改为 true，再执行。脚本结束时会把它改回 false。

```bash
PUMENG_CONFIRM_PUBLISH=1 PUMENG_PUBLISH_NOW='2026-11-06T15:00:00+08:00' \
  bash "$PUMENG_ROOT/scripts/replacement/operator/publish-once.sh"
```

下一次小增量要重新干跑并写入新的两个哈希，再临时开门。`--running-sha` 由脚本填成 `approved_code_sha`，不使用已经前进的页面 HEAD。

## 关闭

`publish-once.sh` 的退出处理会把 `network_publisher` 写回 false。旧入口若仍在安装根，用 `scripts/replacement/operator/disable-old-publish.sh` 把 `publish.sh` 改名为 `publish.sh.disabled-20261106`。`restore-old-publish.sh` 可以移回。这两步不改 routine。

## 回滚

页面字节已经核对成功的提交用新的前进提交收回：把候选改回上一份快照，重新干跑、重绑哈希、再发布一次。

Pages 核对失败时，发布器只在远端 `main` 仍精确等于刚刚推上的那一个提交时收回它。收回命令把这个预期 tip 写进 `git push --force-with-lease=refs/heads/main:<预期>`，由接收端在同一条更新里核对。预期为空表示引用必须还不存在，用来重建被删掉的 `main`。删除同样带着预期 tip。核对不上就停止，不再发送不带预期的强制更新。别人已经快进上去的 tip 会留下来，结果是 `rolled_back=false`，成功基线不写，本机 HEAD 不前进。安装文件里的 `network_publisher` 由 `publish-once.sh` 在结束时改回 false。
