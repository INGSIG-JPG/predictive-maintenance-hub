import { ApiClient } from "./api.js";
import { clear, el, showMessage } from "./dom.js";
import {
  formatTimestamp, nextStatuses, riskClass, riskLabel, validateMachineForm, validateReadingForm,
} from "./format.js";

const api = new ApiClient();
const $ = (id) => document.getElementById(id);
let machines = [];

function errorText(err) {
  const trace = err.traceId ? ` (trace ${err.traceId})` : "";
  return `${err.message || "Unexpected error"}${trace}`;
}

function renderSummary(summary) {
  const levels = summary.by_risk_level;
  const tiles = [
    ["Machines", summary.machines_total],
    ["Critical", levels.critical],
    ["High", levels.high],
    ["Open work orders", summary.open_work_orders],
    ["Readings (24 h)", summary.readings_24h],
    ["Risk model", summary.risk_model],
  ];
  const root = clear($("summary"));
  for (const [label, value] of tiles) root.append(el("div", { class: "tile" }, [el("div", { class: "tile-value" }, value), el("div", { class: "tile-label" }, label)]));
}

function renderMachines(items) {
  const body = clear($("machines-body"));
  if (!items.length) body.append(el("tr", {}, el("td", { colspan: 5, class: "empty" }, "No machines yet. Register one below.")));
  for (const m of items) {
    body.append(el("tr", {}, [
      el("td", {}, m.code), el("td", {}, m.name), el("td", {}, m.machine_type),
      el("td", {}, el("span", { class: `badge ${riskClass(m.latest_risk_level)}` }, riskLabel(m.latest_risk_level, m.latest_risk_score))),
      el("td", {}, formatTimestamp(m.latest_reading_at)),
    ]));
  }
  const select = clear($("reading-machine"));
  select.append(el("option", { value: "" }, "Select machine..."));
  for (const m of items) select.append(el("option", { value: m.code }, `${m.code} - ${m.name}`));
}

function renderWorkOrders(items) {
  const body = clear($("wo-body"));
  if (!items.length) body.append(el("tr", {}, el("td", { colspan: 5, class: "empty" }, "No work orders.")));
  for (const wo of items) {
    const actions = nextStatuses(wo.status).map((status) =>
      el("button", { class: "small", onclick: () => changeStatus(wo.id, status) }, `Mark ${status.replace("_", " ")}`));
    body.append(el("tr", {}, [
      el("td", {}, `#${wo.id}`), el("td", {}, wo.title), el("td", {}, wo.priority),
      el("td", {}, el("span", { class: `badge status-${wo.status}` }, wo.status.replace("_", " "))),
      el("td", {}, actions),
    ]));
  }
}

async function changeStatus(id, status) {
  try {
    await api.updateWorkOrder(id, { status });
    await refresh();
  } catch (err) {
    showMessage($("global-message"), errorText(err), "error");
  }
}

async function refresh() {
  try {
    const [summary, items, orders] = await Promise.all([api.dashboard(), api.listMachines(), api.listWorkOrders()]);
    machines = items;
    renderSummary(summary);
    renderMachines(items);
    renderWorkOrders(orders);
    showMessage($("global-message"), "");
  } catch (err) {
    showMessage($("global-message"), `Could not load data: ${errorText(err)}`, "error");
  }
}

function showFieldErrors(form, errors) {
  for (const input of form.querySelectorAll("[name]")) {
    const slot = form.querySelector(`[data-error-for="${input.name}"]`);
    if (slot) slot.textContent = errors[input.name] || "";
  }
}

$("reading-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const result = validateReadingForm(Object.fromEntries(new FormData(form)));
  showFieldErrors(form, result.errors);
  if (!result.ok) return;
  try {
    const { reading, work_order: workOrder } = await api.submitReading(result.value);
    const extra = workOrder ? ` Work order #${workOrder.id} opened (${workOrder.priority}).` : "";
    showMessage($("reading-message"), `Risk: ${riskLabel(reading.risk_level, reading.risk_score)}.${extra} Trace ${reading.trace_id}`, workOrder ? "warn" : "ok");
    await refresh();
  } catch (err) {
    showMessage($("reading-message"), errorText(err), "error");
  }
});

$("machine-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const result = validateMachineForm(Object.fromEntries(new FormData(form)));
  showFieldErrors(form, result.errors);
  if (!result.ok) return;
  try {
    await api.createMachine(result.value);
    form.reset();
    showMessage($("machine-message"), `Machine ${result.value.code} registered.`, "ok");
    await refresh();
  } catch (err) {
    showMessage($("machine-message"), errorText(err), "error");
  }
});

refresh();
setInterval(refresh, 15000);
