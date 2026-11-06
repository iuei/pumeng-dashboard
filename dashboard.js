(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.PumengDash = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const WARNING = "仅本浏览器，未写回业务源，不等于工作完成";
  const REFRESH_MS = 30000;
  const STORAGE_KEY = "pumeng.local.actions.v1";
  const FIXTURES = Object.create(null);
  FIXTURES.empty = "fixtures/empty.json";
  FIXTURES.stale = "fixtures/stale.json";
  FIXTURES.unknown = "fixtures/unknown.json";

  function resolveDataUrl(fixtureParam, cacheBust) {
    if (fixtureParam && Object.prototype.hasOwnProperty.call(FIXTURES, fixtureParam)) {
      return { url: FIXTURES[fixtureParam], fixtureName: fixtureParam };
    }
    return { url: "data.json?ts=" + cacheBust, fixtureName: null };
  }

  function parseStamp(value) {
    if (!value) return null;
    const match = String(value).match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
    if (!match) return null;
    return new Date(`${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:00+08:00`);
  }

  function classifyFreshness(updatedAt, now) {
    const stamp = parseStamp(updatedAt);
    if (!stamp || Number.isNaN(stamp.getTime())) {
      return { state: "unknown", label: "快照时间未知", ageHours: null };
    }
    const ageHours = (now.getTime() - stamp.getTime()) / 3600000;
    if (ageHours > 24) return { state: "stale_24h", label: "快照时间已超过 24 小时", ageHours };
    if (ageHours > 6) return { state: "stale_6h", label: "快照时间已超过 6 小时", ageHours };
    return { state: "fresh", label: "快照时间在 6 小时内", ageHours };
  }

  function shanghaiDate(date) {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }

  function formatShanghai(date) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date);
    const pick = (type) => {
      const hit = parts.find((part) => part.type === type);
      return hit ? hit.value : "";
    };
    const weekday = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      weekday: "short",
    }).format(date);
    const ymd = `${pick("year")}-${pick("month")}-${pick("day")}`;
    const hm = `${pick("hour")}:${pick("minute")}`;
    return { date: ymd, time: hm, weekday, text: `${ymd} ${hm} ${weekday}` };
  }

  function hasValue(obj, key) {
    return !!obj && Object.prototype.hasOwnProperty.call(obj, key) && obj[key] !== null && obj[key] !== undefined && obj[key] !== "";
  }

  function metricCards(metrics) {
    const source = metrics && typeof metrics === "object" ? metrics : {};
    const tables = source.feishu_tables && typeof source.feishu_tables === "object" ? source.feishu_tables : {};
    const songs = hasValue(tables, "songs") ? String(tables.songs) : "未知";
    const albums = hasValue(tables, "artist_albums") ? String(tables.artist_albums) : "未知";
    return [
      {
        key: "songs_on_platform_approx",
        label: "歌曲在架（约）",
        value: hasValue(source, "songs_on_platform_approx") ? String(source.songs_on_platform_approx) : "未知",
        chip: hasValue(source, "songs_on_platform_approx") ? "约数" : "未核验",
        delta: "较昨日未核验",
        series: "无历史序列",
      },
      {
        key: "play_snapshots",
        label: "播放快照",
        value: hasValue(tables, "play_snapshots") ? String(tables.play_snapshots) : "未知",
        chip: hasValue(tables, "play_snapshots") ? "快照" : "未核验",
        delta: "较昨日未核验",
        series: "无历史序列",
      },
      {
        key: "songs_albums",
        label: "歌曲表 / 专辑表",
        value: `${songs} / ${albums}`,
        chip: hasValue(tables, "songs") || hasValue(tables, "artist_albums") ? "快照" : "未核验",
        delta: "较昨日未核验",
        series: "无历史序列",
      },
      {
        key: "pm_ids_count",
        label: "本批 PM 编号",
        value: hasValue(source, "pm_ids_count") ? String(source.pm_ids_count) : "未知",
        chip: hasValue(source, "pm_ids_count") ? "快照" : "未核验",
        delta: "较昨日未核验",
        series: "无历史序列",
      },
    ];
  }

  function timelineMarker(day) {
    const source = day || {};
    const blobs = []
      .concat(source.did || [], source.closed || [], source.opened || [])
      .map((item) => String(item));
    const opened = Array.isArray(source.opened) && source.opened.length > 0;
    const keyword = blobs.some((item) => item.includes("卡点") || item.includes("阻塞"));
    return { red: opened || keyword, reason: opened ? "opened" : keyword ? "keyword" : "none" };
  }

  function isBlocked(item) {
    return !!(item && item.blocker);
  }

  function blockedDaysLabel(item) {
    if (item && Number.isInteger(item.blocked_days) && item.blocked_days >= 0) {
      return "已阻塞 " + item.blocked_days + " 天";
    }
    return "天数未核验";
  }

  function progressInfo(item) {
    const value = item && item.progress;
    if (typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100) {
      return { known: true, value };
    }
    return { known: false, value: null };
  }

  function collectBucket(data, name) {
    const out = [];
    const seen = new Set();
    function add(item, origin) {
      if (!item || typeof item !== "object") return;
      const key = item.id != null ? "id:" + item.id : "t:" + (item.title || "") + "|" + (item.owner || "");
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ item, origin });
    }
    const today = data && data.today && Array.isArray(data.today[name]) ? data.today[name] : [];
    today.forEach((item) => add(item, "today"));
    const lines = data && data.lines && typeof data.lines === "object" ? data.lines : {};
    Object.keys(lines).forEach((lineName) => {
      const bucket = lines[lineName] && Array.isArray(lines[lineName][name]) ? lines[lineName][name] : [];
      bucket.forEach((item) => add(Object.assign({}, item, { line: item.line || lineName }), "lines"));
    });
    return out;
  }

  function memoryStorage() {
    const map = new Map();
    return {
      getItem: (key) => (map.has(key) ? map.get(key) : null),
      setItem: (key, value) => map.set(key, String(value)),
      removeItem: (key) => map.delete(key),
    };
  }

  function isRecord(item) {
    return !!item && typeof item.recordId === "string" && typeof item.objectId === "string" && typeof item.action === "string";
  }

  function loadRecords(storage) {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (!raw) return { ok: true, records: [] };
      const data = JSON.parse(raw);
      if (!data || !Array.isArray(data.records)) return { ok: false, records: [] };
      return { ok: true, records: data.records.filter(isRecord) };
    } catch (err) {
      return { ok: false, records: [] };
    }
  }

  function persist(storage, records) {
    storage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, records }));
  }

  function newId() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID();
    return "rec-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function addRecord(storage, fields, now) {
    const loaded = loadRecords(storage);
    if (!loaded.ok) {
      const error = new Error("storage_unreadable");
      throw error;
    }
    const record = {
      recordId: newId(),
      action: fields.action,
      objectId: String(fields.objectId),
      objectTitle: String(fields.objectTitle || ""),
      note: String(fields.note || ""),
      savedAt: (now || new Date()).toISOString(),
      snapshotUpdatedAt: fields.snapshotUpdatedAt == null ? null : String(fields.snapshotUpdatedAt),
      sourceUpdatedAt: fields.sourceUpdatedAt == null ? null : String(fields.sourceUpdatedAt),
    };
    persist(storage, loaded.records.concat(record));
    return record;
  }

  function revokeRecord(storage, recordId) {
    const loaded = loadRecords(storage);
    if (!loaded.ok) throw new Error("storage_unreadable");
    persist(storage, loaded.records.filter((item) => item.recordId !== recordId));
  }

  function el(doc, tag, className) {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function pill(doc, className, text) {
    const node = el(doc, "span", "pill " + className);
    node.textContent = text;
    return node;
  }

  function renderNote(doc, text, expandedDefault) {
    const paragraph = el(doc, "p", "note");
    const value = text ? String(text) : "";
    if (!value) {
      paragraph.textContent = "说明未提供";
      return paragraph;
    }
    const chars = Array.from(value);
    if (chars.length <= 42) {
      paragraph.textContent = value;
      return paragraph;
    }
    let open = !!expandedDefault;
    const shown = el(doc, "span");
    const button = el(doc, "button", "linkish");
    button.type = "button";
    function paint() {
      shown.textContent = open ? value : chars.slice(0, 42).join("") + "…";
      button.textContent = open ? "收起" : "展开";
      button.setAttribute("aria-expanded", open ? "true" : "false");
    }
    button.addEventListener("click", () => {
      open = !open;
      paint();
    });
    paint();
    paragraph.append(shown, button);
    return paragraph;
  }

  function openDialog(doc, options) {
    const previously = doc.activeElement;
    const backdrop = el(doc, "div", "backdrop");
    const dialog = el(doc, "div", "dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-labelledby", "dlg-title");
    const title = el(doc, "h3");
    title.id = "dlg-title";
    title.textContent = options.title;
    const warning = el(doc, "p", "warn");
    warning.textContent = WARNING;
    const objectLine = el(doc, "p", "object-line");
    objectLine.textContent = options.objectLabel;
    const stamp = el(doc, "p", "object-line");
    stamp.textContent = options.stampLabel;
    const label = el(doc, "label");
    label.htmlFor = "dlg-note";
    label.textContent = "记录说明";
    const area = el(doc, "textarea");
    area.id = "dlg-note";
    area.placeholder = "只保存在这台浏览器";
    const alert = el(doc, "p", "err");
    alert.setAttribute("role", "alert");
    const actions = el(doc, "div", "actions");
    const save = el(doc, "button", "btn primary");
    save.type = "button";
    save.id = "dlg-save";
    save.textContent = "保存到本浏览器";
    const cancel = el(doc, "button", "btn ghost");
    cancel.type = "button";
    cancel.id = "dlg-cancel";
    cancel.textContent = "取消";
    actions.append(save, cancel);
    label.append(area);
    dialog.append(title, warning, objectLine, stamp, label, alert, actions);
    backdrop.append(dialog);
    const body = doc.body;
    const previousOverflow = body.style.overflow;
    body.style.overflow = "hidden";
    body.append(backdrop);

    function close() {
      doc.removeEventListener("keydown", onKey);
      backdrop.remove();
      body.style.overflow = previousOverflow;
      if (previously && previously.focus) {
        try { previously.focus(); } catch (err) { /* element may be gone after rerender */ }
      }
      if (options.onClose) options.onClose();
    }

    function focusable() {
      return Array.from(dialog.querySelectorAll("button, textarea")).filter((node) => !node.disabled);
    }

    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== "Tab") return;
      const nodes = focusable();
      if (!nodes.length) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (event.shiftKey && doc.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && doc.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    save.addEventListener("click", () => {
      const note = area.value.trim();
      if (!note) {
        alert.textContent = "请填写记录说明。";
        area.focus();
        return;
      }
      try {
        options.onSave(note);
      } catch (err) {
        alert.textContent = "本机存储失败，没有写入。";
        return;
      }
      close();
    });
    cancel.addEventListener("click", close);
    backdrop.addEventListener("click", (event) => {
      if (event.target === backdrop) close();
    });
    doc.addEventListener("keydown", onKey);
    area.focus();
  }

  function render(root, data, options) {
    const doc = root.ownerDocument;
    const source = data && typeof data === "object" ? data : {};
    const now = options.now || new Date();
    const storage = options.storage || memoryStorage();
    const loaded = loadRecords(storage);
    const records = loaded.records;
    const fresh = classifyFreshness(source.updated_at, now);
    const check = formatShanghai(now);
    const updated = parseStamp(source.updated_at);
    const headerDate = updated ? formatShanghai(updated) : null;
    root.replaceChildren();

    const skip = el(doc, "a", "skip");
    skip.href = "#sec-decisions";
    skip.textContent = "跳到拍板事项";
    const wrap = el(doc, "div", "wrap");

    if (options.fixtureName) {
      const banner = el(doc, "p", "fixture-banner");
      banner.textContent = "当前是测试夹具「" + options.fixtureName + "」，不是已发布业务快照。";
      wrap.append(banner);
    }
    if (options.error) {
      const banner = el(doc, "p", "fixture-banner");
      banner.textContent = "快照加载失败：" + options.error + "。下面能显示的字段都按未知处理。";
      wrap.append(banner);
    }

    const header = el(doc, "header", "hdr");
    const titleBlock = el(doc, "div");
    const h1 = el(doc, "h1");
    const star = el(doc, "span", "star");
    star.textContent = "✦";
    star.setAttribute("aria-hidden", "true");
    h1.append(star, doc.createTextNode("谱梦 · 进度监控"));
    const sub = el(doc, "p", "sub");
    sub.textContent = "掌握进度，卡点提前知道。此页只读已发布快照。";
    titleBlock.append(h1, sub);

    const side = el(doc, "div", "hdr-side");
    const badgeRow = el(doc, "div", "badge-row");
    const badge = el(doc, "div", "badge");
    badge.textContent = fresh.state === "unknown" ? "快照时间未知" : fresh.label;
    const date = el(doc, "div", "date");
    date.textContent = headerDate ? headerDate.date + " " + headerDate.weekday : "日期未知";
    badgeRow.append(badge, date);
    const times = el(doc, "dl", "times");
    function row(term, value) {
      const dt = el(doc, "dt");
      dt.textContent = term;
      const dd = el(doc, "dd");
      dd.textContent = value;
      times.append(dt, dd);
    }
    row("本机检查时间", check.text + " · 不是业务变更时间");
    row("updated_at", (source.updated_at ? String(source.updated_at) : "未知") + " · 字段原值");
    row("source_updated_at", (source.source_updated_at ? String(source.source_updated_at) : "未知") + " · 含义未核验");
    side.append(badgeRow, times);
    header.append(titleBlock, side);

    const sync = el(doc, "p", "sync-note");
    sync.textContent = "每 " + Math.round((options.refreshMs || REFRESH_MS) / 1000) + " 秒只重新读取已发布快照，不是业务源实时同步。";
    const localNote = el(doc, "p", "local-note" + (records.length ? " hot" : ""));
    localNote.id = "local-warning";
    localNote.setAttribute("role", "status");
    localNote.textContent = WARNING;
    const help = el(doc, "details", "time-help");
    const helpSummary = el(doc, "summary");
    helpSummary.textContent = "时间字段含义";
    const helpBody = el(doc, "p");
    helpBody.textContent = "本机检查时间是这台浏览器读到快照的时刻，不是业务变更时间。updated_at 和 source_updated_at 是快照文件里的原字段，含义未核验：本仓库没有构建脚本，不能把它们证明成构建时间或业务变更时间。source_updated_at 旁边没有独立的业务变更时钟。";
    help.append(helpSummary, helpBody);

    const decisions = Array.isArray(source.decisions) ? source.decisions.filter((item) => item && typeof item === "object") : [];
    const doing = collectBucket(source, "doing").sort((a, b) => Number(isBlocked(b.item)) - Number(isBlocked(a.item)));
    const blockedCount = doing.filter((entry) => isBlocked(entry.item)).length;
    const activeCount = doing.length - blockedCount;

    const decisionSection = el(doc, "section", "sec");
    decisionSection.id = "sec-decisions";
    const decisionHead = el(doc, "div", "sec-h");
    const decisionTitle = el(doc, "h2");
    const decisionMark = el(doc, "span", "mark");
    decisionMark.textContent = "●";
    decisionTitle.append(decisionMark, doc.createTextNode("需拍板事项"));
    const decisionSub = el(doc, "p");
    decisionSub.textContent = "需要你做出决定。记录只留在本浏览器。";
    decisionHead.append(decisionTitle, decisionSub);
    const decisionGrid = el(doc, "div", "decisions");
    if (!decisions.length) {
      const empty = el(doc, "p", "empty");
      empty.textContent = "暂无待拍板项";
      decisionGrid.append(empty);
    }
    decisions.forEach((item) => {
      decisionGrid.append(renderDecision(doc, item, source, storage, records, now, () => render(root, data, options)));
    });
    decisionSection.append(decisionHead, decisionGrid);

    const todaySection = el(doc, "section", "sec");
    todaySection.id = "sec-today";
    const todayHead = el(doc, "div", "sec-h");
    const todayTitle = el(doc, "h2");
    const todayMark = el(doc, "span", "mark warn");
    todayMark.textContent = "▲";
    todayTitle.append(todayMark, doc.createTextNode("今日卡点"));
    const todaySub = el(doc, "p");
    todaySub.textContent = "红色表示快照写了 blocker。没有天数字段或进度数字时不估算。";
    const legend = el(doc, "div", "legend");
    legend.append(legendItem(doc, "bad", "阻塞项 (" + blockedCount + ")"));
    legend.append(legendItem(doc, "run", "进行中 (" + activeCount + ")"));
    todayHead.append(todayTitle, todaySub, legend);
    const todayGrid = el(doc, "div", "today");
    if (!doing.length) {
      const empty = el(doc, "p", "empty");
      empty.textContent = "今日快照没有进行中事项";
      todayGrid.append(empty);
    }
    doing.forEach((entry) => {
      todayGrid.append(renderDoing(doc, entry, source, storage, records, now, () => render(root, data, options)));
    });
    todaySection.append(todayHead, todayGrid);

    const timelineSection = renderTimeline(doc, source, now);
    const metricSection = renderMetrics(doc, source);
    const otherSection = renderOther(doc, source);
    const localSection = renderLocal(doc, records, loaded.ok, storage, () => render(root, data, options));

    const foot = el(doc, "footer", "foot");
    const disclaimer = el(doc, "p");
    disclaimer.textContent = source.disclaimer ? String(source.disclaimer) : "本页只展示已发布快照里的进度字段。";
    const boundary = el(doc, "p");
    boundary.textContent = "正式回写入口：本仓库不存在，本次未调用。历史说明里的 publish.sh 与 Contents API 不在本仓库。" + WARNING + "。";
    foot.append(disclaimer, boundary);

    wrap.append(header, sync, localNote, help, decisionSection, todaySection, timelineSection, metricSection, otherSection, localSection, foot);
    root.append(skip, wrap);
    root.dataset.ready = "1";
  }

  function legendItem(doc, kind, text) {
    const span = el(doc, "span");
    const dot = el(doc, "i", "dot " + kind);
    span.append(dot, doc.createTextNode(text));
    return span;
  }

  function latestRecord(records, action, objectId) {
    const hits = records.filter((item) => item.action === action && item.objectId === objectId);
    return hits.length ? hits[hits.length - 1] : null;
  }

  function renderDecision(doc, item, source, storage, records, now, rerender) {
    const card = el(doc, "article", "card");
    const title = el(doc, "h3");
    title.textContent = item.title ? String(item.title) : "未命名决定";
    card.append(title, renderNote(doc, item.note, true));
    const meta = el(doc, "div", "meta");
    meta.append(pill(doc, "blue", item.owner ? "待 " + item.owner + " 拍板" : "待拍板"));
    if (item.due || item.suggest_by) meta.append(pill(doc, "muted", "建议最晚 " + String(item.due || item.suggest_by)));
    const button = el(doc, "button", "btn primary");
    button.type = "button";
    button.dataset.action = "decision";
    button.dataset.objectId = item.id ? String(item.id) : "";
    button.textContent = "去决策";
    button.addEventListener("click", () => {
      openDialog(doc, {
        title: "去决策 · 本机记录",
        objectLabel: "对象 " + (item.id || "无 id") + " · " + (item.title || ""),
        stampLabel: "对照快照 updated_at：" + (source.updated_at || "未知") + "；source_updated_at：" + (source.source_updated_at || "未知") + "（含义未核验）",
        onSave(note) {
          addRecord(storage, {
            action: "decision",
            objectId: item.id || item.title || "decision",
            objectTitle: item.title || "",
            note,
            snapshotUpdatedAt: source.updated_at || null,
            sourceUpdatedAt: source.source_updated_at || null,
          }, now);
          rerender();
        },
      });
    });
    meta.append(button);
    card.append(meta);
    const hit = latestRecord(records, "decision", item.id || item.title || "decision");
    if (hit) {
      const flag = el(doc, "p", "local-flag");
      flag.textContent = "本机已记录 · 未写回业务源";
      card.append(flag);
    }
    return card;
  }

  function renderDoing(doc, entry, source, storage, records, now, rerender) {
    const item = entry.item;
    const blocked = isBlocked(item);
    const card = el(doc, "article", "card " + (blocked ? "block" : "prog"));
    const title = el(doc, "h3");
    title.textContent = item.title ? String(item.title) : "未命名事项";
    card.append(title, renderNote(doc, item.note, true));
    const meta = el(doc, "div", "meta");
    if (blocked) {
      meta.append(pill(doc, "red", "阻塞"));
      meta.append(pill(doc, "red", blockedDaysLabel(item)));
    } else {
      meta.append(pill(doc, "blue", "进行中"));
    }
    if (item.line_label || item.line) meta.append(pill(doc, "muted", String(item.line_label || item.line)));
    if (entry.origin === "lines") meta.append(pill(doc, "muted", "补充自 lines"));
    card.append(meta);
    if (blocked) {
      const blocker = el(doc, "p", "blocker-line");
      blocker.textContent = String(item.blocker);
      card.append(blocker);
      const button = el(doc, "button", "btn danger");
      button.type = "button";
      button.dataset.action = "handled";
      button.dataset.objectId = item.id ? String(item.id) : "";
      button.textContent = "标记已处理";
      button.addEventListener("click", () => {
        openDialog(doc, {
          title: "标记已处理 · 本机记录",
          objectLabel: "对象 " + (item.id || "无 id") + " · " + (item.title || ""),
          stampLabel: "对照快照 updated_at：" + (source.updated_at || "未知") + "；source_updated_at：" + (source.source_updated_at || "未知") + "（含义未核验）",
          onSave(note) {
            addRecord(storage, {
              action: "handled",
              objectId: item.id || item.title || "task",
              objectTitle: item.title || "",
              note,
              snapshotUpdatedAt: source.updated_at || null,
              sourceUpdatedAt: source.source_updated_at || null,
            }, now);
            rerender();
          },
        });
      });
      const actions = el(doc, "div", "actions");
      actions.append(button);
      card.append(actions);
    } else {
      const progress = progressInfo(item);
      if (progress.known) {
        const row = el(doc, "div", "bar-row");
        const pct = el(doc, "span", "pct");
        pct.textContent = progress.value + "%";
        const bar = el(doc, "div", "bar");
        const fill = el(doc, "span");
        fill.style.width = progress.value + "%";
        bar.append(fill);
        row.append(pct, bar);
        card.append(row);
      } else {
        const unknown = el(doc, "p", "progress-unknown");
        unknown.textContent = "进度未提供";
        card.append(unknown);
      }
      const eta = el(doc, "p", "eta");
      eta.textContent = item.eta ? "预估 " + String(item.eta) : "预估未提供";
      card.append(eta);
    }
    const hit = latestRecord(records, blocked ? "handled" : "decision", item.id || item.title || "task");
    if (hit && blocked) {
      const flag = el(doc, "p", "local-flag");
      flag.textContent = "本机已标记 · 未写回业务源";
      card.append(flag);
    }
    return card;
  }

  function renderTimeline(doc, source, now) {
    const section = el(doc, "section", "sec");
    section.id = "sec-timeline";
    const head = el(doc, "div", "sec-h");
    const h2 = el(doc, "h2");
    const mark = el(doc, "span", "mark");
    mark.textContent = "●";
    h2.append(mark, doc.createTextNode("个人 7 日时间线"));
    const days = (Array.isArray(source.timeline) ? source.timeline.slice() : []).sort((a, b) => String((a && a.date) || "").localeCompare(String((b && b.date) || "")));
    const dates = days.map((day) => day && day.date).filter(Boolean).slice().sort();
    const sub = el(doc, "p");
    sub.textContent = dates.length
      ? "快照内 " + dates[0] + " — " + dates[dates.length - 1] + "。红点 = 当日 opened 非空，或条目含「卡点」「阻塞」。不是独立阻塞天数。"
      : "快照没有时间线。";
    head.append(h2, sub);
    const panel = el(doc, "div", "panel");
    if (!days.length) {
      const empty = el(doc, "p", "empty");
      empty.textContent = "快照没有时间线";
      panel.append(empty);
    }
    const todayKey = shanghaiDate(now);
    let sawToday = false;
    days.forEach((day) => {
      const row = el(doc, "div", "day");
      const isToday = day && day.date === todayKey;
      if (isToday) {
        row.classList.add("today");
        sawToday = true;
      }
      const date = el(doc, "div", "date");
      date.textContent = dayLabel(day && day.date, isToday);
      const nodeCol = el(doc, "div", "node-col");
      const marker = timelineMarker(day);
      const node = el(doc, "span", "node" + (isToday ? " today" : marker.red ? " red" : ""));
      nodeCol.append(node);
      const body = el(doc, "div", "day-body");
      if (isToday) body.append(todayBox(doc, day));
      else body.append(compactDay(doc, day, marker));
      row.append(date, nodeCol, body);
      panel.append(row);
    });
    if (days.length && !sawToday) {
      const note = el(doc, "p", "empty");
      note.textContent = "快照时间线里没有检查日当天的条目。";
      panel.append(note);
    }
    section.append(head, panel);
    return section;
  }

  function dayLabel(iso, isToday) {
    if (!iso) return "日期未知";
    const stamp = parseStamp(iso + " 12:00");
    if (!stamp) return String(iso);
    const formatted = formatShanghai(stamp);
    const short = formatted.date.slice(5).replace("-", "/");
    return formatted.weekday + " " + short + (isToday ? " (今天)" : "");
  }

  function todayBox(doc, day) {
    const box = el(doc, "div", "today-box");
    const title = el(doc, "h3");
    title.textContent = "今日记录";
    box.append(title);
    box.append(lineList(doc, "完成", day && day.did, false));
    box.append(lineList(doc, "关掉", day && day.closed, false));
    box.append(lineList(doc, "新增", day && day.opened, true));
    return box;
  }

  function lineList(doc, label, items, bad) {
    const paragraph = el(doc, "p", bad ? "block-line" : "done-line");
    const list = Array.isArray(items) ? items.filter((item) => item != null && String(item).trim() !== "") : [];
    paragraph.textContent = label + "：" + (list.length ? list.map((item) => String(item)).join("；") : "无记录");
    return paragraph;
  }

  function compactDay(doc, day, marker) {
    const row = el(doc, "div", "compact");
    const text = el(doc, "p", marker.red ? "bad" : "");
    const did = Array.isArray(day && day.did) ? day.did.length : 0;
    const closed = Array.isArray(day && day.closed) ? day.closed.length : 0;
    const opened = Array.isArray(day && day.opened) ? day.opened.length : 0;
    const bits = [];
    if (did) bits.push(String(day.did[0]));
    text.textContent = bits.length ? bits.join(" ") : (did + closed + opened === 0 ? "无记录" : "做了 " + did + " · 关掉 " + closed + " · 新增 " + opened);
    if (did && (closed || opened)) text.textContent += " · 做了 " + did + " · 关掉 " + closed + " · 新增 " + opened;
    const side = el(doc, "span", marker.red ? "bad strong" : "");
    side.textContent = marker.red ? "有卡点" : "";
    row.append(text, side);
    return row;
  }

  function renderMetrics(doc, source) {
    const section = el(doc, "section", "sec");
    section.id = "sec-metrics";
    const heading = el(doc, "h2", "sr-only");
    heading.textContent = "快照指标";
    const grid = el(doc, "div", "metrics");
    metricCards(source.metrics).forEach((card) => {
      const article = el(doc, "article", "card metric");
      const corner = el(doc, "span", "corner");
      corner.textContent = card.chip;
      const label = el(doc, "div", "ml");
      label.textContent = card.label;
      const num = el(doc, "div", "num");
      num.textContent = card.value;
      const delta = el(doc, "div", "delta");
      delta.textContent = card.delta;
      const series = el(doc, "div", "series");
      series.textContent = card.series;
      article.append(corner, label, num, delta, series);
      grid.append(article);
    });
    section.append(heading, grid);
    return section;
  }

  function renderOther(doc, source) {
    const buckets = [
      ["todo", "待办"],
      ["paused", "暂停"],
      ["done_today", "今日完成"],
    ].map(([name, label]) => ({ name, label, items: collectBucket(source, name) }));
    const details = el(doc, "details", "other");
    details.id = "sec-other";
    const summary = el(doc, "summary");
    summary.textContent = "其他源状态（待办 " + buckets[0].items.length + " · 暂停 " + buckets[1].items.length + " · 今日完成 " + buckets[2].items.length + "）";
    const note = el(doc, "p", "empty");
    note.textContent = "这些条目来自快照的 today，并补上 lines 里没有重复出现的 id。本页不能改业务源。";
    details.append(summary, note);
    buckets.forEach((bucket) => {
      const block = el(doc, "div", "other-block");
      const title = el(doc, "h3");
      title.textContent = bucket.label;
      block.append(title);
      if (!bucket.items.length) {
        const empty = el(doc, "p", "empty");
        empty.textContent = "无";
        block.append(empty);
      }
      bucket.items.forEach((entry) => {
        const row = el(doc, "p", "other-item");
        const item = entry.item;
        row.textContent = (item.title || "未命名") + (item.owner ? " · " + item.owner : "") + (item.blocker ? " · 阻塞：" + item.blocker : "") + (entry.origin === "lines" ? " · 补充自 lines" : "");
        block.append(row);
      });
      details.append(block);
    });
    return details;
  }

  function renderLocal(doc, records, ok, storage, rerender) {
    const section = el(doc, "section", "sec");
    section.id = "sec-local";
    const h2 = el(doc, "h2");
    h2.textContent = "本机记录";
    const note = el(doc, "p");
    note.textContent = ok ? "还没有本机记录时，上面的警告仍然有效。" : "本机记录无法读取，没有覆盖原来的存储。";
    section.append(h2, note);
    if (!records.length) {
      const empty = el(doc, "p", "empty");
      empty.textContent = "还没有本机记录。";
      section.append(empty);
      return section;
    }
    records.forEach((record) => {
      const row = el(doc, "div", "record");
      row.dataset.objectId = record.objectId;
      const title = el(doc, "p", "strong");
      title.textContent = (record.action === "decision" ? "去决策" : "标记已处理") + " · " + record.objectId;
      const name = el(doc, "p");
      name.textContent = record.objectTitle || "";
      const body = el(doc, "p");
      body.textContent = record.note || "";
      const saved = el(doc, "p", "meta-line");
      const when = new Date(record.savedAt);
      saved.textContent = "保存时间 " + (Number.isNaN(when.getTime()) ? record.savedAt : formatShanghai(when).text);
      const stamps = el(doc, "p", "meta-line");
      stamps.textContent = "快照 updated_at " + (record.snapshotUpdatedAt || "未知") + " · source_updated_at " + (record.sourceUpdatedAt || "未知");
      const button = el(doc, "button", "btn ghost");
      button.type = "button";
      button.dataset.revoke = record.recordId;
      button.textContent = "撤销";
      button.addEventListener("click", () => {
        try {
          revokeRecord(storage, record.recordId);
        } catch (err) {
          return;
        }
        rerender();
      });
      row.append(title, name, body, saved, stamps, button);
      section.append(row);
    });
    return section;
  }

  function renderLoadFailure(root, message) {
    render(root, {}, { error: message, storage: memoryStorage(), now: new Date(), refreshMs: REFRESH_MS });
  }

  async function mount(opts) {
    const options = opts || {};
    const doc = options.document || document;
    const win = doc.defaultView || globalThis;
    const root = options.root || doc.getElementById("app");
    const storage = options.storage || win.localStorage;
    const params = new URLSearchParams(win.location.search);
    const resolved = resolveDataUrl(params.get("fixture"), Date.now());
    let data = null;
    let error = null;
    try {
      const response = await win.fetch(resolved.url, { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      data = await response.json();
      if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("snapshot_root_not_object");
    } catch (err) {
      error = err && err.message ? String(err.message) : "加载失败";
    }
    const draw = (next, nextError) => render(root, next || {}, {
      storage,
      now: new Date(),
      fixtureName: resolved.fixtureName,
      error: nextError,
      refreshMs: REFRESH_MS,
    });
    try {
      draw(data, error);
    } catch (err) {
      renderLoadFailure(root, "页面渲染失败");
    }
    if (win.__pumengTimer) win.clearInterval(win.__pumengTimer);
    if (options.liveRefresh !== false) {
      win.__pumengTimer = win.setInterval(async () => {
        if (doc.querySelector(".backdrop")) return;
        try {
          const response = await win.fetch(resolveDataUrl(params.get("fixture"), Date.now()).url, { cache: "no-store" });
          if (!response.ok) throw new Error("HTTP " + response.status);
          const next = await response.json();
          data = next;
          error = null;
        } catch (err) {
          error = "重新读取快照失败";
        }
        try { draw(data, error); } catch (err) { renderLoadFailure(root, "页面渲染失败"); }
      }, REFRESH_MS);
    }
    root.dataset.ready = "1";
  }

  return {
    WARNING,
    REFRESH_MS,
    STORAGE_KEY,
    FIXTURES,
    resolveDataUrl,
    parseStamp,
    classifyFreshness,
    formatShanghai,
    shanghaiDate,
    metricCards,
    timelineMarker,
    isBlocked,
    blockedDaysLabel,
    progressInfo,
    collectBucket,
    memoryStorage,
    loadRecords,
    addRecord,
    revokeRecord,
    render,
    mount,
  };
});
