# 安装与上线核验清单

只写步骤。本文件不授权发布，也没有人在写它的这次提交里执行这些步骤。

11:32 的「可以上线」只说明这一轮界面和更新机制可以被提请上线。真正发布还要等独立验收完成，并且 haole 点名可发布的代码 SHA。检查程序不会自己写出放行文件。

## 安装前

- 源 tasks 仍放在仓库外的目录。不要把 tasks.json、作品库或凭据提交进这个仓库。
- 不覆盖那份真实 tasks。替换入口只有收到 `--tasks` 才读取调用者给出的路径。
- 不新增数据库或 API 权限。发布如果以后启用，只用操作者机器上已经存在的 git 凭据助手，程序不读取 token，也不把 token 写进 remote URL。
- 记录将要安装的代码 SHA。放行文件里的 `approved_code_sha` 必须等于这次运行传入的 `--running-sha`，并且两个哈希必须等于这一次候选。下一份大改不能复用这份放行。

## 检测

```bash
python3 scripts/replacement/safe_publish.py \
  --tasks /绝对路径/tasks.json \
  --baseline data.json \
  --trigger manual \
  --detect \
  --install /绝对路径/install.json \
  --release /绝对路径/release.json \
  --running-sha <haole点名的SHA> \
  --out /tmp/pumeng-detect
```

`detect_ready` 只表示材料齐全。它不会推送，也不会推进成功基线。`publisher_not_enabled` 表示安装文件没有把 `network_publisher` 设为 true。

## 上线前后

上线前：公开站 `data.json` 的 sha256，以及 `main` 的 SHA。上线后：先看 git 是否推到 `main`，再单独看 Pages 上的文件字节是否等于本次候选。两件事都成功才算完成。只有 git 成功时，成功基线不会前进。

回滚：在 `main` 上 revert 该提交，或把页面文件恢复到上线前的 SHA。revert 自己也会触发 Pages，所以同样要有一次明确的发布批准。本清单不执行回滚。

旧 `publish.sh` 里的 `gh auth token` 和 Contents API 回退不能当作这条路径的旁路。那个脚本如果还在原来的机器上，本仓库没有改它，也没有收回它的权限。

## 缺口②：这次代码不能判过

- 运行目录里的旧 `publish.sh` / `build_data.py` 没有在本轮停用，也没有被改写。仓库里的 `scripts/replacement/` 只是可安装的替换包，不等于已经装上。
- 凭据没有收回。分支保护只看到规则集为空和经典接口 403，不能写成已经锁死。
- 真实 `tasks.json` 不入库，历史账号正则不在本包里。获准后的那一次真实推送和 Pages 字节对照都还没有发生，本轮也不该发生。

## 切换计划（仍不执行）

1. 独立验收结束后，由 haole 点名可发布的代码 SHA。
2. 操作者在仓库外写 `install.json`（`network_publisher` 先保持 false）和 `release.json`。`approved_code_sha` 必须等于那个 SHA，也必须等于运行时 `git rev-parse HEAD`。
3. 用 `--detect` 看材料是否齐。齐了再把 `network_publisher` 设为 true，并只在那一次发布时设置 `PUMENG_ALLOW_GITHUB_PUBLISH=1`。没有这个环境变量时，指向 github.com 的远端会被拒绝。
4. 发布器会先做候选字节提交，再推这个提交而不是检出的 `HEAD:main`。Pages 字节不一致或连接失败时，把远端 `main` 退回推送前的 SHA，并且不推进成功基线。
5. 确认旧 `publish.sh` 不再被 routine 调用。这一步不在本仓库里完成。
