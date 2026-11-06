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
