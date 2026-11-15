// Centralised backend communication. Every HTTP call in the UI goes through ApiClient,
// so error handling, headers and URLs live in exactly one place.

export class ApiError extends Error {
  constructor(status, body, traceId) {
    super((body && body.message) || `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = (body && body.error) || "error";
    this.field = (body && body.field) || null;
    this.traceId = traceId || (body && body.trace_id) || null;
  }
}

export class ApiClient {
  constructor({ baseUrl = "", fetchImpl } = {}) {
    this.baseUrl = baseUrl;
    this.fetch = fetchImpl || ((...args) => globalThis.fetch(...args));
  }

  async request(method, path, { query, body } = {}) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query || {})) {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    }
    const qs = params.toString();
    const init = { method, headers: { Accept: "application/json" } };
    if (body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
    const response = await this.fetch(`${this.baseUrl}${path}${qs ? `?${qs}` : ""}`, init);
    const traceId = response.headers && response.headers.get ? response.headers.get("X-Trace-Id") : null;
    let data = null;
    try {
      data = await response.json();
    } catch (_) {
      data = null;
    }
    if (!response.ok) throw new ApiError(response.status, data, traceId);
    return data;
  }

  dashboard() { return this.request("GET", "/api/dashboard/summary"); }
  listMachines() { return this.request("GET", "/api/machines").then((r) => r.items); }
  createMachine(machine) { return this.request("POST", "/api/machines", { body: machine }); }
  listReadings(machineId, limit = 20) {
    return this.request("GET", `/api/machines/${encodeURIComponent(machineId)}/readings`, { query: { limit } }).then((r) => r.items);
  }
  submitReading(reading) { return this.request("POST", "/api/readings", { body: reading }); }
  listWorkOrders(status) { return this.request("GET", "/api/work-orders", { query: { status } }).then((r) => r.items); }
  updateWorkOrder(id, patch) { return this.request("PATCH", `/api/work-orders/${encodeURIComponent(id)}`, { body: patch }); }
  telemetrySummary(windowSeconds = 300) { return this.request("GET", "/api/telemetry/summary", { query: { window: windowSeconds } }); }
  listTraces({ status, journey, limit = 20 } = {}) {
    return this.request("GET", "/api/telemetry/traces", { query: { status, journey, limit } }).then((r) => r.items);
  }
  getTrace(traceId) { return this.request("GET", `/api/telemetry/traces/${encodeURIComponent(traceId)}`); }
  listAlerts() { return this.request("GET", "/api/alerts", { query: { limit: 20 } }).then((r) => r.items); }
  listIncidents() { return this.request("GET", "/api/incidents", { query: { limit: 20 } }).then((r) => r.items); }
}
