import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiClient, ApiError } from "../src/api.js";

function fakeFetch(responses) {
  const calls = [];
  const impl = async (url, init) => {
    calls.push({ url, init });
    const { status = 200, body = {}, headers = {} } = responses.shift();
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: { get: (name) => headers[name] ?? null },
      json: async () => {
        if (body === undefined) throw new Error("no body");
        return body;
      },
    };
  };
  return { impl, calls };
}

test("listMachines unwraps items and calls the right URL", async () => {
  const { impl, calls } = fakeFetch([{ body: { items: [{ id: 1, code: "PUMP-001" }] } }]);
  const api = new ApiClient({ fetchImpl: impl });
  const machines = await api.listMachines();
  assert.deepEqual(machines, [{ id: 1, code: "PUMP-001" }]);
  assert.equal(calls[0].url, "/api/machines");
  assert.equal(calls[0].init.method, "GET");
});

test("submitReading POSTs JSON", async () => {
  const { impl, calls } = fakeFetch([{ status: 201, body: { reading: {}, work_order: null } }]);
  const api = new ApiClient({ fetchImpl: impl });
  await api.submitReading({ machine_code: "PUMP-001", temperature_c: 50 });
  assert.equal(calls[0].url, "/api/readings");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].init.body), { machine_code: "PUMP-001", temperature_c: 50 });
});

test("query parameters skip empty values and are encoded", async () => {
  const { impl, calls } = fakeFetch([{ body: { items: [] } }, { body: { items: [] } }]);
  const api = new ApiClient({ baseUrl: "http://x", fetchImpl: impl });
  await api.listWorkOrders(undefined);
  await api.listTraces({ status: "error", journey: "ingest_reading", limit: 5 });
  assert.equal(calls[0].url, "http://x/api/work-orders");
  assert.equal(calls[1].url, "http://x/api/telemetry/traces?status=error&journey=ingest_reading&limit=5");
});

test("path parameters are URL encoded", async () => {
  const { impl, calls } = fakeFetch([{ body: {} }]);
  await new ApiClient({ fetchImpl: impl }).getTrace("a/b c");
  assert.equal(calls[0].url, "/api/telemetry/traces/a%2Fb%20c");
});

test("non-2xx responses throw ApiError with status, code, field and trace id", async () => {
  const { impl } = fakeFetch([
    { status: 422, body: { error: "validation_error", message: "temperature_c must be a number", field: "temperature_c" }, headers: { "X-Trace-Id": "abc123" } },
  ]);
  const api = new ApiClient({ fetchImpl: impl });
  await assert.rejects(api.submitReading({}), (err) => {
    assert.ok(err instanceof ApiError);
    assert.equal(err.status, 422);
    assert.equal(err.code, "validation_error");
    assert.equal(err.field, "temperature_c");
    assert.equal(err.traceId, "abc123");
    assert.match(err.message, /temperature_c/);
    return true;
  });
});

test("a failed response without a JSON body still produces a useful error", async () => {
  const { impl } = fakeFetch([{ status: 502, body: undefined }]);
  await assert.rejects(new ApiClient({ fetchImpl: impl }).dashboard(), (err) => {
    assert.equal(err.status, 502);
    assert.match(err.message, /502/);
    return true;
  });
});

test("updateWorkOrder sends PATCH to the work order URL", async () => {
  const { impl, calls } = fakeFetch([{ body: { id: 7 } }]);
  await new ApiClient({ fetchImpl: impl }).updateWorkOrder(7, { status: "done" });
  assert.equal(calls[0].url, "/api/work-orders/7");
  assert.equal(calls[0].init.method, "PATCH");
});
