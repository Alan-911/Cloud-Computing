// Defined workload for the latency SLO (Phase 09 acceptance).
//
//   100 requests/s (constant arrival rate) for 3 minutes, after a 30 s ramp-up,
//   through the public entry point (nginx), with this mix:
//     60% GET  /api/v1/items/{id}     read one
//     25% GET  /api/v1/items?limit=20 list a page
//     10% POST /api/v1/items          create (API key)
//      5% PATCH /api/v1/items/{id}    update (API key)
//
// Pass: p95 < 200 ms, p99 < 500 ms, failed requests < 0.5% (the 99.5% SLO).
//
//   docker run --rm --network host -v "$PWD/tests/performance/k6:/k6" \
//     -e BASE_URL=http://localhost -e API_KEY=... grafana/k6:2.4.0 run /k6/load.js
//
// Env: BASE_URL, API_KEY, RATE (default 100), DURATION (default 3m), SUMMARY (path).

import http from "k6/http";
import { check } from "k6";
import { SharedArray } from "k6/data";
import exec from "k6/execution";

const BASE = (__ENV.BASE_URL || "http://localhost").replace(/\/$/, "");
const API = `${BASE}/api`;
const KEY = __ENV.API_KEY || "";
const RATE = Number(__ENV.RATE || 100);
const DURATION = __ENV.DURATION || "3m";
const SEED_ITEMS = 200;

const JSON_HEADERS = { "Content-Type": "application/json" };
const WRITE_HEADERS = Object.assign({ "X-API-Key": KEY }, JSON_HEADERS);

export const options = {
  discardResponseBodies: false,
  scenarios: {
    warmup: {
      executor: "ramping-arrival-rate",
      startRate: 5,
      timeUnit: "1s",
      preAllocatedVUs: 20,
      maxVUs: 200,
      stages: [{ duration: "30s", target: RATE }],
      tags: { phase: "warmup" },
    },
    steady: {
      executor: "constant-arrival-rate",
      startTime: "30s",
      rate: RATE,
      timeUnit: "1s",
      duration: DURATION,
      preAllocatedVUs: 50,
      maxVUs: 400,
      tags: { phase: "steady" },
    },
  },
  // Thresholds apply to the steady phase only; the warm-up just fills caches/pools.
  thresholds: {
    "http_req_duration{phase:steady}": ["p(95)<200", "p(99)<500"],
    "http_req_failed{phase:steady}": ["rate<0.005"],
    "checks{phase:steady}": ["rate>0.995"],
    // Per-operation latency, reported in the summary (generous bounds, never the gate).
    "http_req_duration{phase:steady,op:read}": ["p(95)<10000"],
    "http_req_duration{phase:steady,op:list}": ["p(95)<10000"],
    "http_req_duration{phase:steady,op:create}": ["p(95)<10000"],
    "http_req_duration{phase:steady,op:update}": ["p(95)<10000"],
    dropped_iterations: ["count<50"],
    "http_reqs{phase:steady}": ["count>0"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

export function setup() {
  if (!KEY) throw new Error("API_KEY is required (writes need it)");
  const run = Date.now().toString(36);
  const ids = [];
  for (let i = 0; i < SEED_ITEMS; i++) {
    const r = http.post(`${API}/v1/items`, JSON.stringify({ name: `seed-${run}-${i}` }), {
      headers: WRITE_HEADERS,
      tags: { phase: "setup" },
    });
    if (r.status === 201) ids.push(r.json("id"));
  }
  if (ids.length < SEED_ITEMS * 0.95) throw new Error(`seeding failed: ${ids.length}/${SEED_ITEMS}`);
  return { ids, run };
}

export default function (data) {
  const phase = exec.scenario.name === "steady" ? "steady" : "warmup";
  const id = data.ids[Math.floor(Math.random() * data.ids.length)];
  const roll = Math.random();

  if (roll < 0.6) {
    const r = http.get(`${API}/v1/items/${id}`, { tags: { op: "read", phase } });
    check(r, { "read 200": (x) => x.status === 200 }, { phase });
  } else if (roll < 0.85) {
    const offset = Math.floor(Math.random() * 10) * 20;
    const r = http.get(`${API}/v1/items?limit=20&offset=${offset}`, { tags: { op: "list", phase } });
    check(r, { "list 200": (x) => x.status === 200 }, { phase });
  } else if (roll < 0.95) {
    const name = `load-${data.run}-${exec.vu.idInTest}-${exec.scenario.iterationInTest}-${Math.random().toString(36).slice(2, 8)}`;
    const r = http.post(`${API}/v1/items`, JSON.stringify({ name }), {
      headers: WRITE_HEADERS,
      tags: { op: "create", phase },
    });
    check(r, { "create 201": (x) => x.status === 201 }, { phase });
  } else {
    const r = http.patch(
      `${API}/v1/items/${id}`,
      JSON.stringify({ description: `updated ${Date.now()}` }),
      { headers: WRITE_HEADERS, tags: { op: "update", phase } },
    );
    check(r, { "update 200": (x) => x.status === 200 }, { phase });
  }
}

export function handleSummary(data) {
  const out = { stdout: textSummary(data) };
  if (__ENV.SUMMARY) out[__ENV.SUMMARY] = JSON.stringify(data, null, 2);
  return out;
}

function textSummary(data) {
  const m = data.metrics;
  const d = (name) => (m[name] ? m[name].values : null);
  const fmt = (v) => (v === undefined || v === null ? "-" : `${v.toFixed(1)} ms`);
  const steady = d("http_req_duration{phase:steady}") || {};
  const failed = d("http_req_failed{phase:steady}") || {};
  const lines = [
    "",
    `Defined workload: ${RATE} req/s for ${DURATION} through ${BASE}`,
    `  steady requests : ${(d("http_reqs{phase:steady}") || {}).count}`,
    `  p50 / p95 / p99 : ${fmt(steady.med)} / ${fmt(steady["p(95)"])} / ${fmt(steady["p(99)"])}  (max ${fmt(steady.max)})`,
    `  failed requests : ${((failed.rate || 0) * 100).toFixed(3)}%`,
  ];
  for (const op of ["read", "list", "create", "update"]) {
    const v = d(`http_req_duration{phase:steady,op:${op}}`);
    if (v) lines.push(`  ${op.padEnd(7)} p95     : ${fmt(v["p(95)"])}`);
  }
  const verdicts = Object.entries(m)
    .filter(([, v]) => v.thresholds)
    .flatMap(([name, v]) => Object.entries(v.thresholds).map(([t, r]) => `  ${r.ok ? "PASS" : "FAIL"}  ${name}: ${t}`));
  return lines.concat(["", "Thresholds:"], verdicts, [""]).join("\n");
}
