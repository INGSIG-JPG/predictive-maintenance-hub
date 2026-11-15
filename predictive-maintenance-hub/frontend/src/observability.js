import { ApiClient } from "./api.js";
import { clear, el, showMessage } from "./dom.js";
import { formatEpoch, formatMs, formatPercent, formatTimestamp, waterfall } from "./format.js";

const api = new ApiClient();
const $ = (id) => document.getElementById(id);
const JOURNEY = "ingest_reading";
let selectedTrace = null;

function renderJourney(summary) {
  const stats = summary.journeys[JOURNEY] || { requests: 0, errors: 0, error_ratio: 0, p50_ms: 0, p95_ms: 0 };
  const tiles = [
    ["Requests (5 min)", stats.requests],
    ["Error ratio", formatPercent(stats.error_ratio)],
    ["p50 latency", formatMs(stats.p50_ms)],
    ["p95 latency", formatMs(stats.p95_ms)],
  ];
  const root = clear($("journey"));
  for (const [label, value] of tiles) {
    const bad = label === "Error ratio" && stats.error_ratio > 0.05;
    root.append(el("div", { class: `tile${bad ? " tile-bad" : ""}` }, [el("div", { class: "tile-value" }, value), el("div", { class: "tile-label" }, label)]));
  }
}

function renderTraces(items) {
  const body = clear($("traces-body"));
  if (!items.length) body.append(el("tr", {}, el("td", { colspan: 6, class: "empty" }, "No traces yet. Send a reading from the dashboard.")));
  for (const t of items) {
    body.append(el("tr", { class: t.trace_id === selectedTrace ? "selected" : "", onclick: () => openTrace(t.trace_id) }, [
      el("td", {}, formatEpoch(t.started_at)), el("td", {}, t.route || "-"),
      el("td", {}, el("span", { class: `badge ${t.status === "error" ? "risk-critical" : "risk-low"}` }, String(t.status_code ?? "-"))),
      el("td", {}, formatMs(t.duration_ms)), el("td", { class: "mono" }, t.trace_id.slice(0, 12) + "..."),
      el("td", {}, t.error_message || ""),
    ]));
  }
}

async function openTrace(traceId) {
  selectedTrace = traceId;
  try {
    const trace = await api.getTrace(traceId);
    $("trace-title").textContent = `Trace ${trace.trace_id}`;
    const rows = waterfall(trace.spans);
    const spans = clear($("spans"));
    for (const s of rows) {
      spans.append(el("div", { class: "span-row" }, [
        el("div", { class: "span-name" }, `${s.name}${s.status === "error" ? " (error)" : ""}`),
        el("div", { class: "span-track" }, el("div", { class: `span-bar${s.status === "error" ? " bad" : ""}`, style: `left:${s.left}%;width:${s.width}%` })),
        el("div", { class: "span-ms" }, formatMs(s.duration_ms)),
        s.error_message ? el("div", { class: "span-error" }, s.error_message) : null,
      ]));
    }
    const logs = clear($("logs"));
    for (const l of trace.logs) {
      logs.append(el("div", { class: `log log-${l.level}` }, [
        el("span", { class: "mono" }, `${formatEpoch(l.ts)} ${l.level.toUpperCase()} `), l.message, " ",
        el("span", { class: "mono dim" }, JSON.stringify(l.fields)),
      ]));
    }
  } catch (err) {
    showMessage($("obs-message"), `Could not load trace: ${err.message}`, "error");
  }
}

function renderAlerts(alerts, incidents) {
  const list = clear($("alerts"));
  if (!alerts.length) list.append(el("li", { class: "empty" }, "No alerts."));
  for (const a of alerts) {
    list.append(el("li", {}, [el("span", { class: `badge ${a.status === "firing" ? "risk-critical" : "risk-low"}` }, a.status), ` ${a.rule}: ${a.summary} `, el("span", { class: "dim" }, formatTimestamp(a.fired_at))]));
  }
  const inc = clear($("incidents"));
  if (!incidents.length) inc.append(el("li", { class: "empty" }, "No incidents."));
  for (const i of incidents) {
    inc.append(el("li", {}, [el("span", { class: `badge ${i.status === "resolved" ? "risk-low" : "risk-high"}` }, i.status), ` ${i.summary} `, el("span", { class: "dim" }, formatTimestamp(i.created_at))]));
  }
}

async function refresh() {
  try {
    const [summary, traces, alerts, incidents] = await Promise.all([
      api.telemetrySummary(300), api.listTraces({ limit: 15 }), api.listAlerts(), api.listIncidents(),
    ]);
    renderJourney(summary);
    renderTraces(traces);
    renderAlerts(alerts, incidents);
    showMessage($("obs-message"), "");
  } catch (err) {
    showMessage($("obs-message"), `Could not load telemetry: ${err.message}`, "error");
  }
}

refresh();
setInterval(refresh, 5000);
