# 这次测试证据

被测代码是 `00cc93abe2889fe6e9666a2bbf9b3a476c9ea2e5`。写入这些日志的提交在它之后，不要把后一个 SHA 当成被测树。

命令是在该 SHA 上执行的，stdout 和 stderr 经 `tee` 同时写入仓库 `artifacts/` 和 `/opt/cursor/artifacts/`：

```bash
python3 -m unittest discover -s tests -v 2>&1 | tee artifacts/test-python.log artifacts/test-python-00cc93abe288.log artifacts/test-python-replacement-final.log /opt/cursor/artifacts/test-python.log /opt/cursor/artifacts/test-python-00cc93abe288.log /opt/cursor/artifacts/test-python-replacement-final.log
node --test tests/test_dashboard.js 2>&1 | tee artifacts/test-node.log artifacts/test-node-00cc93abe288.log artifacts/test-node-replacement-final.log /opt/cursor/artifacts/test-node.log /opt/cursor/artifacts/test-node-00cc93abe288.log /opt/cursor/artifacts/test-node-replacement-final.log
NODE_PATH=".test-tools/node_modules${NODE_PATH:+:$NODE_PATH}" node tests/browser_check.cjs 2>&1 | tee artifacts/test-browser.log artifacts/test-browser-00cc93abe288.log artifacts/test-browser-replacement-final.log /opt/cursor/artifacts/test-browser.log /opt/cursor/artifacts/test-browser-00cc93abe288.log /opt/cursor/artifacts/test-browser-replacement-final.log
```

请看带 SHA 或 `replacement-final` 的文件。同名的 `test-python.log` 这次也重写了，但自动取件曾经拿到过旧的 20 项日志。

核对结果写在 `artifacts/test-run-00cc93a.json`：两处 Python 日志 sha256 都是 `ef792ceb2eccd91d3c68c80141bcc7fd766cb89bbb96d252c964278a6df6b65e`，内容含 `test_replacement.ReplacementTests` 6 项，结尾是 `Ran 26 tests in 0.139s` 和 `OK`。Node 10 项通过。浏览器输出 `BROWSER_OK`。

默认态截图由同一次浏览器进程写出，不是事后改的数字。`desktop-1920x1080.png` 的 mtime 是 `2026-11-06T03:30:28Z`。`browser-check.json` 里 `defaultState` 为 true，`viewport` 1080，`metricsBottom` 1040.578125，`openDisclosures` 0。手机截图是同一次运行的 390 宽整页。

## 受控适配器那次

被测代码是 `761e95fb62784d90b316132a4e2e14764b5e0719`。请看 `artifacts/test-python-761e95fb6278.log` 和 `artifacts/test-python-adapter-final.log`，不要拿上面的 `00cc93a` 日志代替。两处目录的 sha256 都是 `10f071b480c4b8358816c70d7935d34ecb7644343c9202a8c4db0ee884526ab5`。结尾是 `Ran 32 tests in 0.136s` 和 `OK`，其中替换包 6 项、受控适配器 6 项。Node 与浏览器的对应文件名同样带 `761e95fb6278` 和 `adapter-final`。对照表是 `artifacts/test-run-761e95f.json`。这次默认态截图 mtime 是 `2026-11-06T03:37:44Z`，视口断言仍是 1080 与 `metricsBottom` 1040.578125。写入日志的提交若更新了本文件，那个 SHA 不是被测树。

## 返修 B1–B3 / M1

被测代码是 `100451dfbffca33da2fbe989d77d66fc88661caf`。请看 `artifacts/test-python-100451dfbffc.log` 和 `artifacts/test-python-repair-final.log`。两处目录 sha256 都是 `15f0f27d4600b1519627502e3669695eab450c52265313cf6d3f79774f9b0e9b`。结尾是 `Ran 34 tests in 0.252s` 和 `OK`。本地 bare 回滚与过期锁回收这两条都在这份日志里，状态是 ok。Node、浏览器文件名同样带 `100451dfbffc` 和 `repair-final`。对照表是 `artifacts/test-run-100451d.json`。

这次默认态截图 mtime 是 `2026-11-06T04:00:55Z`。`browser-check.json` 的 `fontPx` 为标题 43、区标题 27、卡标题 24、正文 20、按钮 20、指标 42、标签 16。`metricsBottom` 仍不超过 1080，`openDisclosures` 为 0。390 与 320 的截图是同一次运行写出的。后续如果只把本段说明提交进去，那个 SHA 不是被测树。

## 空 main 与回滚被拒

被测代码是 `b665cc4d8677235c728dd8ced390d8efa0dbaffa`。请看 `artifacts/test-python-b665cc4d8677.log` 和 `artifacts/test-python-b1-final.log`。两处目录 sha256 都是 `dc7f6ac5ec0c6521281bd46d1a504aa99eeebf0623f84078cea23220a9f54877`。结尾是 `Ran 36 tests in 0.408s` 和 `OK`。证明用例是 `test_empty_bare_deletes_main_when_pages_do_not_match` 与 `test_rejected_rollback_does_not_report_push_success`，都是 ok。已有 main 且允许强制回滚的用例 `test_file_bare_pushes_candidate_bytes_and_rolls_back_when_pages_mismatch` 仍是 ok。对照表是 `artifacts/test-run-b665cc4.json`。这次默认态截图 mtime 是 `2026-11-06T04:22:00Z`，字号仍是 43/27/24/20/20/42，`metricsBottom` 是 960.109375。写入本段的提交不是被测树。远端只用 `file://` 临时 bare，没有推 github.com 的 main。
