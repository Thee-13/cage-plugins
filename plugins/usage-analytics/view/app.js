"use strict";

const labels = {
  en: {
    title: "Usage Analytics", scope: "Claude Code usage recorded in this environment",
    refresh: "Refresh", period: "Period", today: "Today", days7: "Last 7 days",
    days30: "Last 30 days", days90: "Last 90 days", apply: "Apply", model: "Model",
    allModels: "All models", modelHint: "200 models shown. You can enter any exact model ID.",
    totals: "Usage totals", input: "Fresh input", output: "Output", read: "Cache read",
    write: "Cache creation", rate: "Cache hit rate", requests: "Requests",
    formula: "Cache hit rate = cache read ÷ (fresh input + cache read + cache creation).",
    trend: "Daily trend", dailyValues: "Daily values", day: "Date", logs: "Request records",
    logNote: "Records come from deduplicated usage counters.", time: "Time", client: "Client",
    empty: "No requests for these filters.", previous: "Previous", next: "Next", pages: "Pages",
    loading: "Reading usage records…", missing_database: "No usage database yet. Refresh native usage statistics, then retry.",
    unsupported_schema: "This usage database format is unsupported.",
    busy: "The usage database is busy or the query timed out. Retry or choose a shorter period.",
    invalid_filters: "Check the selected period and model.",
    unavailable: "Usage data is unavailable. Check that the environment and its usage statistics are ready.",
  },
  "zh-CN": {
    title: "用量分析", scope: "当前环境记录的 Claude Code 用量",
    refresh: "刷新", period: "时间范围", today: "今天", days7: "最近 7 天",
    days30: "最近 30 天", days90: "最近 90 天", apply: "应用", model: "模型",
    allModels: "全部模型", modelHint: "列表显示前 200 个模型，也可输入完整的模型 ID。",
    totals: "用量汇总", input: "新输入", output: "输出", read: "缓存读取",
    write: "缓存创建", rate: "缓存命中率", requests: "请求数",
    formula: "缓存命中率 = 缓存读取 ÷（新输入 + 缓存读取 + 缓存创建）。",
    trend: "每日趋势", dailyValues: "查看每日数值", day: "日期", logs: "请求日志",
    logNote: "记录来自去重后的原生用量计数。", time: "时间", client: "客户端",
    empty: "当前筛选条件下没有请求。", previous: "上一页", next: "下一页", pages: "分页",
    loading: "正在读取用量记录…", missing_database: "用量数据库尚未生成。请刷新原生用量统计后重试。",
    unsupported_schema: "当前用量数据库格式不受支持。",
    busy: "数据库繁忙或查询超时。请重试或缩短时间范围。",
    invalid_filters: "请检查时间范围和模型。",
    unavailable: "暂时无法读取用量。请确认环境已启动且原生用量统计可用。",
  },
  "zh-TW": {
    title: "用量分析", scope: "目前環境記錄的 Claude Code 用量",
    refresh: "重新整理", period: "時間範圍", today: "今天", days7: "最近 7 天",
    days30: "最近 30 天", days90: "最近 90 天", apply: "套用", model: "模型",
    allModels: "所有模型", modelHint: "清單會顯示前 200 個模型，也可以輸入完整的模型 ID。",
    totals: "用量總覽", input: "新輸入", output: "輸出", read: "快取讀取",
    write: "快取建立", rate: "快取命中率", requests: "請求數",
    formula: "快取命中率 = 快取讀取 ÷（新輸入 + 快取讀取 + 快取建立）。",
    trend: "每日趨勢", dailyValues: "查看每日數值", day: "日期", logs: "請求記錄",
    logNote: "記錄來自去除重複項目後的原生用量計數。", time: "時間", client: "用戶端",
    empty: "目前篩選條件下沒有請求。", previous: "上一頁", next: "下一頁", pages: "分頁",
    loading: "正在讀取用量記錄…", missing_database: "用量資料庫尚未建立。請重新整理原生用量統計後重試。",
    unsupported_schema: "目前的用量資料庫格式不受支援。",
    busy: "資料庫忙碌或查詢逾時。請重試或縮短時間範圍。",
    invalid_filters: "請檢查時間範圍和模型。",
    unavailable: "暫時無法讀取用量。請確認環境已啟動且原生用量統計可用。",
  },
};

const byId = (id) => document.getElementById(id);
const counters = ["input", "output", "read", "write"];
const metricKeys = [...counters, "cache_hit_rate", "requests"];
const logKeys = ["time", "model", "client", ...counters];
const trendKeys = ["day", ...metricKeys];
const themeKeys = ["paper", "ink", "strong", "muted", "line", "chrome", "input", "hover", "focus", "danger"];
const chart = byId("chart");
const tooltip = byId("chart-detail");
const controls = ["days", "model", "apply", "refresh", "previous", "next"];
const pending = new Map();
let sequence = 0;
let copy = labels.en;
let numbers;
let compact;
let percent;
let data;
let activeFilters = {days: 7, model: ""};
let busy = false;
let initialized = false;
let selectedDay = null;

function rpc(method, params) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error("unavailable"));
    }, 12000);
    pending.set(id, {resolve, reject, timer});
    window.parent.postMessage({jsonrpc: "2.0", id, method, params}, "*");
  });
}

window.addEventListener("message", ({source, data: message}) => {
  if (source !== window.parent || message?.jsonrpc !== "2.0") return;
  if (message.method === "ui/themeChanged") {
    applyTheme(message.params);
    return;
  }
  if (message.method === "ui/visibilityChanged" && message.params?.visible && initialized && !busy) {
    load(1, activeFilters);
    return;
  }
  const request = pending.get(message.id);
  if (!request) return;
  pending.delete(message.id);
  clearTimeout(request.timer);
  if (message.error) request.reject(new Error("unavailable"));
  else request.resolve(message.result);
});

function applyTheme(theme) {
  const root = document.documentElement;
  root.dataset.theme = theme?.scheme === "dark" ? "dark" : "light";
  for (const key of themeKeys) {
    root.style.removeProperty(`--${key}`);
    const value = theme?.tokens?.[key];
    if (value && CSS.supports("color", value)) root.style.setProperty(`--${key}`, value);
  }
  drawChart();
}

function makeRow(record, keys, heading = false) {
  const row = document.createElement("tr");
  for (const key of keys) {
    const cell = document.createElement(heading ? "th" : "td");
    if (heading) cell.scope = "col";
    if (metricKeys.includes(key)) cell.classList.add("numeric");
    const value = record[key];
    cell.textContent = heading ? copy[key === "cache_hit_rate" ? "rate" : key] : format(key, value);
    row.append(cell);
  }
  return row;
}

function format(key, value) {
  if (value == null) return "—";
  if (key === "cache_hit_rate") return percent.format(value);
  return typeof value === "number" ? numbers.format(value) : value;
}

function localize(locale) {
  const code = Object.hasOwn(labels, locale) ? locale : "en";
  copy = labels[code];
  document.documentElement.lang = code;
  document.title = copy.title;
  numbers = new Intl.NumberFormat(code);
  compact = new Intl.NumberFormat(code, {notation: "compact", maximumFractionDigits: 1});
  percent = new Intl.NumberFormat(code, {style: "percent", maximumFractionDigits: 1});
  for (const node of document.querySelectorAll("[data-label]")) node.textContent = copy[node.dataset.label];
  byId("model").placeholder = copy.allModels;
  byId("metrics").setAttribute("aria-label", copy.totals);
  byId("pagination").setAttribute("aria-label", copy.pages);
  byId("trend-headers").replaceWith(Object.assign(makeRow({}, trendKeys, true), {id: "trend-headers"}));
  byId("log-headers").replaceWith(Object.assign(makeRow({}, logKeys, true), {id: "log-headers"}));
}

function chartBounds() {
  return {x: 54, y: 12, w: chart.clientWidth - 70, h: chart.clientHeight - 39};
}

function drawChart() {
  if (!data || byId("report").hidden) return;
  const {x, y, w, h} = chartBounds();
  if (w < 70 || h < 40) return;
  const ratio = window.devicePixelRatio || 1;
  chart.width = Math.round(chart.clientWidth * ratio);
  chart.height = Math.round(chart.clientHeight * ratio);
  const ctx = chart.getContext("2d");
  ctx.scale(ratio, ratio);
  const style = getComputedStyle(chart);
  const color = (key) => style.getPropertyValue(`--${key}`).trim();
  const points = data.trend;
  const max = Math.max(4, ...points.flatMap((day) => counters.map((key) => day[key])));
  const step = Math.max(1, Math.ceil(max / 4));
  const atX = (index) => x + (points.length === 1 ? w / 2 : w * index / (points.length - 1));
  const atY = (value) => y + h - h * value / (step * 4);

  ctx.font = "11px system-ui";
  ctx.fillStyle = color("muted");
  ctx.strokeStyle = color("line");
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  for (let i = 0; i <= 4; i++) {
    const lineY = atY(i * step);
    ctx.beginPath();
    ctx.moveTo(x, lineY);
    ctx.lineTo(x + w, lineY);
    ctx.stroke();
    ctx.fillText(compact.format(i * step), x - 6, lineY);
  }
  ctx.textAlign = "center";
  const ticks = Math.min(points.length, Math.max(2, Math.floor(w / 62)));
  for (let i = 0; i < ticks; i++) {
    const index = ticks === 1 ? 0 : Math.round(i * (points.length - 1) / (ticks - 1));
    ctx.fillText(points[index].day.slice(5), Math.min(x + w - 4, atX(index)), y + h + 16);
  }

  if (selectedDay !== null) {
    ctx.beginPath();
    ctx.moveTo(atX(selectedDay), y);
    ctx.lineTo(atX(selectedDay), y + h);
    ctx.stroke();
  }
  for (const key of counters) {
    ctx.strokeStyle = ctx.fillStyle = color(`series-${key}`);
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach((day, i) => {
      if (i === 0) ctx.moveTo(atX(i), atY(day[key]));
      else ctx.lineTo(atX(i), atY(day[key]));
    });
    ctx.stroke();
    const index = selectedDay ?? (points.length === 1 ? 0 : null);
    if (index !== null) {
      ctx.beginPath();
      ctx.arc(atX(index), atY(points[index][key]), 4, 0, 2 * Math.PI);
      ctx.fill();
    }
  }
}

function render(report) {
  data = report;
  selectedDay = null;
  tooltip.hidden = true;
  for (const key of metricKeys) byId(`total-${key}`).textContent = format(key, report.totals[key]);
  byId("models").replaceChildren(...report.models.map((name) => {
    const option = document.createElement("option");
    option.value = name;
    return option;
  }));
  byId("model-hint").hidden = !report.models_truncated;
  byId("trend-rows").replaceChildren(...report.trend.map((day) => makeRow(day, trendKeys)));
  byId("logs").replaceChildren(...report.rows.map((row) => makeRow(row, logKeys)));
  byId("page").textContent = `${numbers.format(report.page)} / ${numbers.format(report.last_page)}`;
  byId("pagination").hidden = report.last_page === 1;
  byId("empty").hidden = report.rows.length !== 0;
  byId("log-table").hidden = report.rows.length === 0;
  byId("status").textContent = [`${report.start} – ${report.end}`, report.timezone, activeFilters.model]
    .filter(Boolean).join(" · ");
  byId("report").hidden = false;
  drawChart();
}

async function load(page, filters) {
  if (busy) return;
  busy = true;
  const previousFilters = activeFilters;
  activeFilters = filters;
  controls.forEach((id) => { byId(id).disabled = true; });
  const changingPage = data && filters === previousFilters && page !== data.page;
  if (!changingPage) byId("report").hidden = true;
  byId("report").setAttribute("aria-busy", "true");
  byId("model-hint").hidden = true;
  const status = byId("status");
  status.textContent = copy.loading;
  status.classList.remove("error");
  data = null;
  try {
    const response = await rpc("tools/call", {name: "usage_analytics_report", arguments: {...filters, page}});
    const text = response?.content?.find((item) => item.type === "text")?.text;
    if (response?.isError) throw new Error(text || "unavailable");
    render(response?.structuredContent ?? JSON.parse(text));
  } catch (error) {
    byId("report").hidden = true;
    status.textContent = Object.hasOwn(copy, error.message) ? copy[error.message] : copy.unavailable;
    status.classList.add("error");
  } finally {
    busy = false;
    byId("report").setAttribute("aria-busy", "false");
    controls.slice(0, 4).forEach((id) => { byId(id).disabled = false; });
    byId("previous").disabled = !data || data.page <= 1;
    byId("next").disabled = !data || data.page >= data.last_page;
  }
}

function applyFilters() {
  load(1, {days: Number(byId("days").value), model: byId("model").value.trim()});
}

byId("apply").addEventListener("click", applyFilters);
byId("model").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing) applyFilters();
});
byId("refresh").addEventListener("click", applyFilters);
byId("previous").addEventListener("click", () => load(data.page - 1, activeFilters));
byId("next").addEventListener("click", () => load(data.page + 1, activeFilters));
chart.addEventListener("pointermove", (event) => {
  if (!data) return;
  const {x, w} = chartBounds();
  if (w < 70) return;
  const position = event.clientX - chart.getBoundingClientRect().left;
  const index = Math.round(Math.max(0, Math.min(1, (position - x) / w)) * (data.trend.length - 1));
  if (selectedDay === index) return;
  selectedDay = index;
  const day = data.trend[index];
  tooltip.textContent = [day.day, ...counters.map((key) => `${copy[key]}  ${format(key, day[key])}`)].join("\n");
  tooltip.hidden = false;
  tooltip.style.left = `${Math.max(0, Math.min(chart.clientWidth - tooltip.offsetWidth, position + 12))}px`;
  drawChart();
});
chart.addEventListener("pointerleave", () => {
  selectedDay = null;
  tooltip.hidden = true;
  drawChart();
});
new ResizeObserver(drawChart).observe(chart);

async function start() {
  try {
    const init = await rpc("ui/initialize", {protocolVersion: 1});
    localize(init.locale);
    applyTheme(init.theme);
    initialized = true;
    await load(1, activeFilters);
  } catch {
    byId("status").textContent = copy.unavailable;
  }
}

start();
