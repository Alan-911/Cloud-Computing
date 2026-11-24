// Capacity test: ramp the arrival rate until latency degrades, to find the knee.
//
// Targets the API service directly (http://api:8000 on the Compose network),
// bypassing nginx: nginx deliberately caps one client IP at 300 req/s, which would
// otherwise measure the rate limiter instead of the service.
//
// Rate bands, 45 s each after a 15 s ramp: 50, 100, 200, 300, 400, 600, 800 req/s.
// Same read-heavy mix as load.js. Latency and failures are reported per band; no
// threshold gates the run (this measures, it does not pass/fail).
//
// Env: BASE_URL (default http://api:8000), API_KEY, SUMMARY, and for short runs
// BANDS (comma-separated req/s), STEP and RAMP (seconds).

import http from "k6/http";
import { check } from "k6";
import exec from "k6/execution";
import { Rate } from "k6/metrics";

// 503 = shed by the API (fast rejection at capacity); ok = served successfully.
const shed = new Rate("shed");
const ok = new Rate("served_ok");

const BASE = (__ENV.BASE_URL || "http://api:8000").replace(/\/$/, "");
const API = `${BASE}/api`;
const KEY = __ENV.API_KEY || "";
const BANDS = (__ENV.BANDS || "50,100,200,300,400,600,800").split(",").map(Number);
const STEP = Number(__ENV.STEP || 45); // seconds per band
const RAMP = Number(__ENV.RAMP || 15);

const WRITE_HEADERS = { "Content-Type": "application/json", "X-API-Key": KEY };

const stages = [];
for (const rate of BANDS) {
  stages.push({ duration: `${RAMP}s`, target: rate });
  stages.push({ duration: `${STEP}s`, target: rate });
}

const thresholds = {};
for (const rate of BANDS) {
  // Placeholder thresholds create per-band sub-metrics in the summary.
  thresholds[`http_req_duration{band:${rate}}`] = ["p(95)<60000"];
  thresholds[`http_req_failed{band:${rate}}`] = ["rate<=1"];
  thresholds[`http_reqs{band:${rate}}`] = ["count>=0"];
  thresholds[`shed{band:${rate}}`] = ["rate<=1"];
  thresholds[`served_ok{band:${rate}}`] = ["rate<=1"];
}

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-arrival-rate",
      startRate: 10,
      timeUnit: "1s",
      preAllocatedVUs: 100,
      maxVUs: 1500,
      stages,
    },
  },
  thresholds,
  summaryTrendStats: ["med", "p(95)", "p(99)", "max"],
};

// The band a request belongs to: only the plateau of each step counts; the ramp
// between bands is tagged "ramp" and excluded.
function band() {
  const t = (Date.now() - exec.scenario.startTime) / 1000;
  const i = Math.floor(t / (RAMP + STEP));
  if (i >= BANDS.length) return "ramp";
  return t - i * (RAMP + STEP) >= RAMP ? String(BANDS[i]) : "ramp";
}

export function setup() {
  const ids = [];
  for (let i = 0; i < 200; i++) {
    const r = http.post(`${API}/v1/items`, JSON.stringify({ name: `stress-seed-${Date.now()}-${i}` }), {
      headers: WRITE_HEADERS,
    });
    if (r.status === 201) ids.push(r.json("id"));
  }
  if (ids.length < 190) throw new Error(`seeding failed: ${ids.length}`);
  return { ids };
}

export default function (data) {
  const tags = { band: band() };
  const p = { tags, timeout: "10s" };
  const w = { tags, timeout: "10s", headers: WRITE_HEADERS };
  const id = data.ids[Math.floor(Math.random() * data.ids.length)];
  const roll = Math.random();
  let r;
  if (roll < 0.6) r = http.get(`${API}/v1/items/${id}`, p);
  else if (roll < 0.85) r = http.get(`${API}/v1/items?limit=20`, p);
  else if (roll < 0.95)
    r = http.post(`${API}/v1/items`, JSON.stringify({ name: `s-${exec.vu.idInTest}-${exec.scenario.iterationInTest}` }), w);
  else r = http.patch(`${API}/v1/items/${id}`, JSON.stringify({ description: "x" }), w);
  check(r, { "2xx": (x) => x.status >= 200 && x.status < 300 });
  shed.add(r.status === 503, tags);
  ok.add(r.status >= 200 && r.status < 300, tags);
}

export function handleSummary(data) {
  const m = data.metrics;
  const rows = ["", "Capacity (per sustained rate band):", "  target    reqs    p50 ms   p95 ms   p99 ms   failed   shed(503)  served/s"];
  for (const rate of BANDS) {
    const d = m[`http_req_duration{band:${rate}}`];
    const f = m[`http_req_failed{band:${rate}}`];
    const n = m[`http_reqs{band:${rate}}`];
    const sh = m[`shed{band:${rate}}`];
    const okr = m[`served_ok{band:${rate}}`];
    const servedPerS = n && okr ? ((n.values.count * okr.values.rate) / STEP).toFixed(0) : "-";
    if (!d) continue;
    const v = d.values;
    rows.push(
      `  ${String(rate).padStart(4)}/s  ${String(n ? n.values.count : "-").padStart(6)}  ${v.med.toFixed(1).padStart(7)}  ${v["p(95)"]
        .toFixed(1)
        .padStart(7)}  ${v["p(99)"].toFixed(1).padStart(7)}   ${((f ? f.values.rate : 0) * 100).toFixed(2).padStart(6)}%   ${((sh ? sh.values.rate : 0) * 100).toFixed(1).padStart(6)}%   ${String(servedPerS).padStart(7)}`,
    );
  }
  rows.push(`  dropped iterations (load generator could not keep up): ${m.dropped_iterations ? m.dropped_iterations.values.count : 0}`, "");
  const out = { stdout: rows.join("\n") };
  if (__ENV.SUMMARY) out[__ENV.SUMMARY] = JSON.stringify(data, null, 2);
  return out;
}
