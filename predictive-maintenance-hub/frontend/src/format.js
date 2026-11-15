// Pure helpers (no DOM, no network) so they can be unit tested with `node --test`.

export const RISK_LEVELS = ["low", "medium", "high", "critical"];

export function riskClass(level) {
  return RISK_LEVELS.includes(level) ? `risk-${level}` : "risk-unknown";
}

export function riskLabel(level, score) {
  if (!RISK_LEVELS.includes(level)) return "No data";
  return typeof score === "number" ? `${level} (${score.toFixed(0)})` : level;
}

export function formatTimestamp(iso) {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

export function formatEpoch(seconds) {
  if (typeof seconds !== "number") return "-";
  return new Date(seconds * 1000).toISOString().slice(11, 23);
}

export function formatPercent(ratio) {
  if (typeof ratio !== "number") return "-";
  return `${(ratio * 100).toFixed(1)}%`;
}

export function formatMs(value) {
  if (typeof value !== "number") return "-";
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value.toFixed(1)} ms`;
}

const LIMITS = {
  temperature_c: [-50, 500],
  vibration_mm_s: [0, 200],
  pressure_bar: [0, 400],
};

// Mirrors the backend validation so the user gets instant feedback; the backend stays authoritative.
export function validateReadingForm(raw) {
  const errors = {};
  const code = String(raw.machine_code || "").trim();
  if (!code) errors.machine_code = "Select a machine";
  const values = {};
  for (const [field, [lo, hi]] of Object.entries(LIMITS)) {
    const text = String(raw[field] ?? "").trim();
    const num = Number(text);
    if (text === "" || !Number.isFinite(num)) errors[field] = "Enter a number";
    else if (num < lo || num > hi) errors[field] = `Must be between ${lo} and ${hi}`;
    else values[field] = num;
  }
  const ok = Object.keys(errors).length === 0;
  return { ok, errors, value: ok ? { machine_code: code, ...values } : null };
}

export function validateMachineForm(raw) {
  const errors = {};
  const code = String(raw.code || "").trim().toUpperCase();
  if (!/^[A-Z0-9][A-Z0-9-]{2,31}$/.test(code)) errors.code = "3-32 chars: letters, digits or '-'";
  const name = String(raw.name || "").trim();
  if (!name) errors.name = "Name is required";
  const ok = Object.keys(errors).length === 0;
  return {
    ok,
    errors,
    value: ok ? { code, name, machine_type: raw.machine_type || "other", location: String(raw.location || "").trim() } : null,
  };
}

export function nextStatuses(status) {
  return { open: ["in_progress", "done"], in_progress: ["done", "open"], done: [] }[status] || [];
}

// Build a waterfall layout (left/width in percent) for the spans of one trace.
export function waterfall(spans) {
  if (!spans.length) return [];
  const start = Math.min(...spans.map((s) => s.started_at));
  const end = Math.max(...spans.map((s) => s.started_at + s.duration_ms / 1000));
  const total = Math.max(end - start, 0.000001);
  return spans.map((s) => ({
    ...s,
    left: ((s.started_at - start) / total) * 100,
    width: Math.max((s.duration_ms / 1000 / total) * 100, 0.5),
  }));
}
