import { test } from "node:test";
import assert from "node:assert/strict";
import {
  formatMs, formatPercent, formatTimestamp, nextStatuses, riskClass, riskLabel,
  validateMachineForm, validateReadingForm, waterfall,
} from "../src/format.js";

test("riskClass maps known levels and falls back to unknown", () => {
  assert.equal(riskClass("critical"), "risk-critical");
  assert.equal(riskClass("low"), "risk-low");
  assert.equal(riskClass(null), "risk-unknown");
  assert.equal(riskClass("weird"), "risk-unknown");
});

test("riskLabel includes the rounded score", () => {
  assert.equal(riskLabel("high", 72.4), "high (72)");
  assert.equal(riskLabel("low"), "low");
  assert.equal(riskLabel(null), "No data");
});

test("formatting helpers handle missing values", () => {
  assert.equal(formatTimestamp(null), "-");
  assert.equal(formatTimestamp("not a date"), "-");
  assert.equal(formatTimestamp("2026-01-02T03:04:05+00:00"), "2026-01-02 03:04 UTC");
  assert.equal(formatPercent(0.0525), "5.3%");
  assert.equal(formatPercent(undefined), "-");
  assert.equal(formatMs(12.34), "12.3 ms");
  assert.equal(formatMs(1500), "1.50 s");
});

test("validateReadingForm accepts a valid form and converts numbers", () => {
  const r = validateReadingForm({ machine_code: " PUMP-001 ", temperature_c: "45", vibration_mm_s: "1.2", pressure_bar: "6" });
  assert.equal(r.ok, true);
  assert.deepEqual(r.value, { machine_code: "PUMP-001", temperature_c: 45, vibration_mm_s: 1.2, pressure_bar: 6 });
});

test("validateReadingForm reports every invalid field", () => {
  const r = validateReadingForm({ machine_code: "", temperature_c: "hot", vibration_mm_s: "-3", pressure_bar: "" });
  assert.equal(r.ok, false);
  assert.equal(r.value, null);
  assert.deepEqual(Object.keys(r.errors).sort(), ["machine_code", "pressure_bar", "temperature_c", "vibration_mm_s"]);
});

test("validateReadingForm rejects out of range values", () => {
  const r = validateReadingForm({ machine_code: "A-1", temperature_c: "9999", vibration_mm_s: "1", pressure_bar: "1" });
  assert.match(r.errors.temperature_c, /between/);
});

test("validateMachineForm normalises the code and validates the name", () => {
  const ok = validateMachineForm({ code: "pump-001", name: "Pump", machine_type: "pump", location: " Plant A " });
  assert.equal(ok.ok, true);
  assert.deepEqual(ok.value, { code: "PUMP-001", name: "Pump", machine_type: "pump", location: "Plant A" });
  const bad = validateMachineForm({ code: "x", name: "  " });
  assert.equal(bad.ok, false);
  assert.ok(bad.errors.code && bad.errors.name);
});

test("nextStatuses mirrors the backend state machine", () => {
  assert.deepEqual(nextStatuses("open"), ["in_progress", "done"]);
  assert.deepEqual(nextStatuses("done"), []);
  assert.deepEqual(nextStatuses("zzz"), []);
});

test("waterfall positions spans relative to the trace", () => {
  const rows = waterfall([
    { name: "http.request", started_at: 100, duration_ms: 100 },
    { name: "risk.score", started_at: 100.02, duration_ms: 50 },
  ]);
  assert.equal(rows[0].left, 0);
  assert.ok(Math.abs(rows[0].width - 100) < 1e-6);
  assert.ok(Math.abs(rows[1].left - 20) < 1e-6);
  assert.ok(Math.abs(rows[1].width - 50) < 1e-6);
  assert.deepEqual(waterfall([]), []);
});
