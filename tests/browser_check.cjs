const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const root = path.resolve(__dirname, "..");
const { chromium } = require(path.join(root, ".test-tools/node_modules/playwright-core"));
const data = JSON.parse(fs.readFileSync(path.join(root, "data.json"), "utf8"));
const outDir = path.join(root, "artifacts");
fs.mkdirSync(outDir, { recursive: true });

function startServer() {
  return new Promise((resolve, reject) => {
    const child = spawn("python3", ["-u", "-m", "http.server", "0", "--bind", "127.0.0.1"], {
      cwd: root,
      env: { ...process.env, PYTHONUNBUFFERED: "1" },
    });
    let buffered = "";
    const timer = setTimeout(() => reject(new Error("server did not start")), 8000);
    function onData(chunk) {
      buffered += chunk.toString();
      const match = buffered.match(/port\s+(\d+)/i);
      if (match) {
        clearTimeout(timer);
        resolve({ child, port: match[1] });
      }
    }
    child.stderr.on("data", onData);
    child.stdout.on("data", onData);
    child.on("exit", (code) => reject(new Error("server exited " + code)));
  });
}

async function overflow(page) {
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
}

async function assertNoOverflow(page, width, height, label) {
  await page.setViewportSize({ width, height });
  await page.waitForTimeout(50);
  const box = await overflow(page);
  if (box.scrollWidth > box.clientWidth + 1) {
    throw new Error(`${label} overflow ${box.scrollWidth} > ${box.clientWidth}`);
  }
  return box;
}

(async () => {
  const server = await startServer();
  const base = `http://127.0.0.1:${server.port}`;
  const browser = await chromium.launch({
    executablePath: "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  const page = await browser.newPage({ locale: "zh-CN", viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("response", (res) => {
    if (res.status() < 400) return;
    if (res.url().endsWith("/favicon.ico")) return;
    errors.push(res.status() + " " + res.url());
  });
  page.on("request", (req) => {
    const host = new URL(req.url()).hostname;
    if (host !== "127.0.0.1" && host !== "localhost") errors.push("offsite " + req.url());
  });

  try {
    await page.goto(base + "/index.html", { waitUntil: "networkidle" });
    await page.waitForSelector("#app[data-ready='1']");
    const text = await page.locator("body").innerText();
    for (const needle of ["夜行地铁", "浮光", "56.8", "歌词最终版未确认"]) {
      if (text.includes(needle)) throw new Error("example copy leaked: " + needle);
    }
    if (!text.includes(data.decisions[0].title)) throw new Error("real decision title missing");
    if (!text.includes(data.updated_at)) throw new Error("updated_at missing");
    if (!text.includes("source_updated_at")) throw new Error("source field label missing");
    if (!text.includes("含义未核验")) throw new Error("unverified label missing");
    if (!text.includes("只重新读取已发布快照")) throw new Error("refresh copy missing");
    if (!text.includes("仅本浏览器，未写回业务源，不等于工作完成")) throw new Error("local warning missing");
    if (!text.includes("天数未核验")) throw new Error("blocked days should be unverified");
    if (!text.includes("进度未提供")) throw new Error("progress should be unverified");
    if (!text.includes("较昨日未核验")) throw new Error("metric delta should be unverified");
    const ids = await page.$$eval("section[id]", (nodes) => nodes.map((node) => node.id));
    const expected = ["sec-decisions", "sec-today", "sec-timeline", "sec-metrics"];
    if (ids.slice(0, 4).join() !== expected.join()) throw new Error("section order " + ids.join());
    if (await page.locator("#sec-lines").count()) throw new Error("team switch section present");

    const columnsAt = async (width, height) => {
      await page.setViewportSize({ width, height });
      const grids = await page.evaluate(() => ({
        decisions: getComputedStyle(document.querySelector(".decisions")).gridTemplateColumns,
        today: getComputedStyle(document.querySelector(".today")).gridTemplateColumns,
        metrics: getComputedStyle(document.querySelector(".metrics")).gridTemplateColumns,
      }));
      return { width, ...grids };
    };
    const columns = {
      desktop: await columnsAt(1920, 1080),
      mobile: await columnsAt(390, 844),
    };
    if (columns.mobile.decisions.split(" ").length !== 1) throw new Error("mobile decisions not stacked: " + columns.mobile.decisions);
    if (columns.mobile.today.split(" ").length !== 1) throw new Error("mobile today not stacked: " + columns.mobile.today);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.screenshot({ path: path.join(outDir, "desktop-1920x1080.png") });
    await page.screenshot({ path: path.join(outDir, "desktop-full.png"), fullPage: true });
    for (const [width, height] of [[1920, 1080], [1280, 800], [768, 1024], [390, 844], [320, 700]]) {
      await assertNoOverflow(page, width, height, "home " + width);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(outDir, "mobile-390x844.png"), fullPage: true });

    await page.setViewportSize({ width: 1920, height: 1080 });
    for (let i = 0; i < 40; i += 1) {
      const action = await page.evaluate(() => document.activeElement && document.activeElement.dataset.action);
      if (action === "decision") break;
      await page.keyboard.press("Tab");
    }
    const focused = await page.evaluate(() => document.activeElement && document.activeElement.dataset.action);
    if (focused !== "decision") throw new Error("keyboard did not reach 去决策");
    await page.keyboard.press("Enter");
    await page.waitForSelector("[role='dialog']");
    await page.keyboard.press("Escape");
    await page.waitForSelector("[role='dialog']", { state: "detached" });

    await page.click("[data-action='decision']");
    await page.click("#dlg-save");
    if (!(await page.locator("[role='alert']").innerText()).includes("请填写记录说明")) {
      throw new Error("empty decision was accepted");
    }
    await page.fill("#dlg-note", "界面自测记录");
    await page.click("#dlg-save");
    await page.waitForSelector("#sec-local .record");
    const recordText = await page.locator("#sec-local .record").first().innerText();
    if (!recordText.includes(data.decisions[0].id)) throw new Error("record missing object id");
    if (!recordText.includes(data.updated_at)) throw new Error("record missing snapshot stamp");
    if (!recordText.includes("界面自测记录")) throw new Error("record missing note");
    const hot = await page.locator("#local-warning").innerText();
    if (!hot.includes("仅本浏览器，未写回业务源，不等于工作完成")) throw new Error("hot warning missing");
    await page.screenshot({ path: path.join(outDir, "local-decision-1920.png") });
    await page.click("[data-revoke]");
    await page.waitForFunction(() => !document.querySelector("#sec-local .record"));

    await page.click("[data-action='handled']");
    await page.fill("#dlg-note", "界面自测已处理");
    await page.click("#dlg-save");
    await page.waitForSelector("#sec-local .record");
    const handled = await page.locator("#sec-local .record").innerText();
    if (!handled.includes("标记已处理")) throw new Error("handled record missing");
    await page.click("[data-revoke]");
    await page.waitForFunction(() => !document.querySelector("#sec-local .record"));

    await page.setViewportSize({ width: 390, height: 844 });
    await page.click("[data-action='decision']");
    const dialogBox = await page.locator(".dialog").boundingBox();
    const view = page.viewportSize();
    if (!dialogBox || dialogBox.x < -1 || dialogBox.x + dialogBox.width > view.width + 1) {
      throw new Error("dialog overflows mobile");
    }
    await page.keyboard.press("Escape");

    async function fixture(name, needles) {
      await page.goto(base + "/index.html?fixture=" + name, { waitUntil: "networkidle" });
      await page.waitForSelector("#app[data-ready='1']");
      const body = await page.locator("body").innerText();
      if (!body.includes("测试夹具「" + name + "」")) throw new Error(name + " banner missing");
      for (const needle of needles) {
        if (!body.includes(needle)) throw new Error(name + " missing " + needle);
      }
      await assertNoOverflow(page, 390, 844, name + " mobile");
      await assertNoOverflow(page, 1920, 1080, name + " desktop");
    }
    await fixture("empty", ["暂无待拍板项", "今日快照没有进行中事项", "快照时间未知"]);
    await fixture("stale", ["快照时间已超过 24 小时"]);
    await fixture("unknown", ["天数未核验", "进度未提供", "快照时间未知"]);

    if (errors.length) throw new Error(errors.join("\n"));
    fs.writeFileSync(path.join(outDir, "browser-check.json"), JSON.stringify({ ok: true, base, columns }, null, 2));
    console.log("BROWSER_OK");
  } finally {
    await browser.close();
    server.child.kill("SIGTERM");
  }
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
