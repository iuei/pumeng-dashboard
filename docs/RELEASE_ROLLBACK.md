# 发布与回滚（只写步骤，本次不执行）

这次任务没有获准发布。下面的步骤留作以后。没有人在这次运行它们，脚本里也没有能把它们跑起来的开关。

## 为什么合并会变成线上变更

GitHub Pages 的源是 `main` 的 `/`，类型 legacy。`github-pages` 环境还允许名为 `gh-pages` 的分支，但远程现在没有这个分支。合并到 `main` 会触发自带的 `pages-build-deployment`，公开站 `https://iuei.github.io/pumeng-dashboard/` 会换成新的 `index.html`。`data.json` 在这个分支里没有改。

## 以后若要发布

必须先有 liu 对**那一次**发布的明确批准。本任务里的批准文件只约束模拟发布，不能当成上线批准。

1. 确认要上的提交 SHA，并确认 `data.json` 相对当时的线上仍然是有意的内容。
2. 由人把获准的提交合并到 `main`。不要从本脚本、Contents API 或仓库外的 `publish.sh` 旁路推送，除非那次批准写明了入口。
3. 看 Pages 构建对应的是这个 SHA，再打开公开站核对。构建本身就会更新线上。

## 回滚

1. 在 `main` 上 revert 那次合并，或把页面文件恢复到发布前的提交。调查时线上与 `5dad88fd079d33fef8b222327ec43cfc466d2161` 一致。
2. 这次分支不修改 `data.json`。回滚页面时不要顺手回退后来别人提交的业务快照。
3. revert 提交进入 `main` 后，Pages 会再构建一次，公开站回到旧页面。这一步同样是生产写入，没有新的批准就不能做。

## 不要做的事

- 不要推 `main` 或新建 `gh-pages`。
- 不要 `workflow_dispatch` 那个 Pages workflow。
- 不要给本仓库加 `schedule` / cron。
- 不要把 `--simulate` 的输出目录拷进 `main` 来冒充发布。
