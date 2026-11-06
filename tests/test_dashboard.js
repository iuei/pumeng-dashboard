const test = require("node:test");
const assert = require("node:assert/strict");
const dash = require("../dashboard.js");

test("warning sentence is exact", () => {
  assert.equal(dash.WARNING, "仅本浏览器，未写回业务源，不等于工作完成");
});

test("fixture urls stay inside the repo allowlist", () => {
  assert.deepEqual(dash.resolveDataUrl("empty", 1), { url: "fixtures/empty.json", fixtureName: "empty" });
  assert.equal(dash.resolveDataUrl("../data.json", 1).fixtureName, null);
  assert.equal(dash.resolveDataUrl("http://example.invalid/data.json", 1).url.startsWith("data.json?ts="), true);
  assert.equal(dash.resolveDataUrl("__proto__", 1).fixtureName, null);
  assert.equal(dash.resolveDataUrl("constructor", 1).fixtureName, null);
  for (const value of Object.values(dash.FIXTURES)) {
    assert.equal(value.startsWith("fixtures/"), true);
    assert.equal(value.includes(".."), false);
  }
});

test("freshness boundaries use the snapshot clock, not a business SLA name", () => {
  const now = new Date("2026-11-06T02:00:00Z"); // 2026-11-06 10:00 Asia/Shanghai
  assert.equal(dash.classifyFreshness("2026-11-06 08:07 Asia/Shanghai", now).state, "fresh");
  assert.equal(dash.classifyFreshness("2026-11-06 04:00", now).state, "fresh");
  assert.equal(dash.classifyFreshness("2026-11-06 03:59", now).state, "stale_6h");
  assert.equal(dash.classifyFreshness("2026-11-05 10:00", now).state, "stale_6h");
  assert.equal(dash.classifyFreshness("2026-11-05 09:59", now).state, "stale_24h");
  assert.equal(dash.classifyFreshness("not-a-date", now).state, "unknown");
  assert.equal(dash.classifyFreshness("", now).label, "快照时间未知");
});

test("shanghai formatting does not follow the machine zone", () => {
  const formatted = dash.formatShanghai(new Date("2026-11-06T00:07:00Z"));
  assert.equal(formatted.date, "2026-11-06");
  assert.equal(formatted.time, "08:07");
});

test("metrics use snapshot fields and unknown instead of example numbers", () => {
  const cards = dash.metricCards({});
  assert.deepEqual(cards.map((card) => card.label), ["歌曲在架（约）", "播放快照", "歌曲表 / 专辑表", "本批 PM 编号"]);
  assert.equal(cards.every((card) => card.value === "未知" || card.value === "未知 / 未知"), true);
  assert.equal(cards.every((card) => card.delta === "较昨日未核验" && card.series === "无历史序列"), true);
  const real = dash.metricCards({
    songs_on_platform_approx: 4700,
    pm_ids_count: 0,
    feishu_tables: { play_snapshots: 3213, songs: 4 },
  });
  assert.equal(real[0].value, "4700");
  assert.equal(real[0].chip, "约数");
  assert.equal(real[1].value, "3213");
  assert.equal(real[2].value, "4 / 未知");
  assert.equal(real[3].value, "0");
  assert.equal(JSON.stringify(cards).includes("56.8"), false);
  assert.equal(JSON.stringify(cards).includes("完成进度"), false);
});

test("timeline red dot is opened or keyword, not a fabricated percent", () => {
  assert.equal(dash.timelineMarker({ did: [], closed: [], opened: ["新事项"] }).reason, "opened");
  assert.equal(dash.timelineMarker({ did: ["这里有卡点"], closed: [], opened: [] }).reason, "keyword");
  assert.equal(dash.timelineMarker({ did: ["普通记录"], closed: [], opened: [] }).red, false);
  assert.equal(dash.timelineMarker({}).red, false);
});

test("missing progress and blocked days stay unverified", () => {
  assert.equal(dash.progressInfo({ title: "x" }).known, false);
  assert.equal(dash.progressInfo({ progress: "62%" }).known, false);
  assert.equal(dash.progressInfo({ progress: 35 }).value, 35);
  assert.equal(dash.blockedDaysLabel({ blocker: "缺" }), "天数未核验");
  assert.equal(dash.blockedDaysLabel({ blocked_days: 2 }), "已阻塞 2 天");
  assert.equal(dash.isBlocked({ blocker: "缺" }), true);
  assert.equal(dash.isBlocked({ title: "x" }), false);
});

test("lines bucket does not duplicate today ids", () => {
  const data = {
    today: { doing: [{ id: "a", title: "甲" }] },
    lines: { pumeng: { doing: [{ id: "a", title: "甲重复" }, { id: "b", title: "乙" }] } },
  };
  const items = dash.collectBucket(data, "doing");
  assert.deepEqual(items.map((entry) => entry.item.id), ["a", "b"]);
  assert.equal(items[1].origin, "lines");
});

test("local records store identity and snapshot stamps and can be revoked", () => {
  const storage = dash.memoryStorage();
  const now = new Date("2026-11-06T01:30:00Z");
  const saved = dash.addRecord(storage, {
    action: "decision",
    objectId: "ask-1",
    objectTitle: "要决定的事",
    note: "先记在浏览器",
    snapshotUpdatedAt: "2026-11-06 08:07 Asia/Shanghai",
    sourceUpdatedAt: "2026-11-06 08:06 Asia/Shanghai",
  }, now);
  assert.equal(saved.objectId, "ask-1");
  assert.equal(saved.savedAt, now.toISOString());
  assert.equal(saved.snapshotUpdatedAt, "2026-11-06 08:07 Asia/Shanghai");
  const loaded = dash.loadRecords(storage);
  assert.equal(loaded.records.length, 1);
  dash.revokeRecord(storage, saved.recordId);
  assert.equal(dash.loadRecords(storage).records.length, 0);
});

test("corrupt local storage is not overwritten by a read", () => {
  const storage = dash.memoryStorage();
  storage.setItem(dash.STORAGE_KEY, "{");
  const loaded = dash.loadRecords(storage);
  assert.equal(loaded.ok, false);
  assert.equal(storage.getItem(dash.STORAGE_KEY), "{");
});
