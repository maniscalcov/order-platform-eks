// k6 steady-load script for chaos experiments.
//
// Unlike order-api-load.js (a ramp to 150 VUs that deliberately overwhelms
// the workers), this holds a CONSTANT, modest load that the whole saga can
// keep up with: ~10 VUs * ~2 iterations/s = ~20 orders/s, below the
// payment-worker ceiling (~34 msgs/s at 6 replicas, sequential, ~175ms per
// simulated charge). That makes "queues near 0, 0% errors" the steady state,
// so any effect of an injected fault (pod-kill, DNS failure) stands out
// clearly on the dashboard instead of being buried in a growing backlog.
//
// No thresholds on purpose: during a chaos run errors are EXPECTED. The SLO
// recording rules / burn-rate alerts are the pass/fail signal, not k6.
//
// Run in-cluster with the existing Job by storing this script under the key
// the Job expects:
//   kubectl create configmap k6-scripts -n order-platform "--from-file=order-api-load.js=load-test/chaos-load.js"
//   kubectl apply -f load-test\k6-job.yaml
//
// Tunables (env vars): VUS (default 10), DURATION (default 25m).

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";

const ordersCreated = new Counter("orders_created");
const ordersFailed = new Counter("orders_failed");

// Must match the seeded SKUs in terraform/dynamodb.tf.
const SKUS = [
  "SKU-WIDGET-001",
  "SKU-WIDGET-002",
  "SKU-GADGET-010",
  "SKU-GADGET-011",
  "SKU-DOODAD-100",
];

export const options = {
  scenarios: {
    steady: {
      executor: "constant-vus",
      vus: parseInt(__ENV.VUS || "10", 10),
      duration: __ENV.DURATION || "25m",
    },
  },
};

function randomOrder() {
  const itemCount = Math.floor(Math.random() * 3) + 1;
  const shuffled = SKUS.slice().sort(() => Math.random() - 0.5);
  const items = shuffled.slice(0, itemCount).map((sku) => ({
    sku: sku,
    quantity: Math.floor(Math.random() * 3) + 1,
    unit_price_cents: (Math.floor(Math.random() * 90) + 10) * 100,
  }));
  return {
    customer_id: `cust-${Math.floor(Math.random() * 10000)}`,
    items: items,
  };
}

export default function () {
  const res = http.post(`${BASE_URL}/orders`, JSON.stringify(randomOrder()), {
    headers: { "Content-Type": "application/json" },
    tags: { name: "POST /orders" },
    timeout: "10s", // fail fast instead of k6's 60s default during a fault
  });

  const ok = check(res, { "status is 201": (r) => r.status === 201 });
  if (ok) {
    ordersCreated.add(1);
  } else {
    ordersFailed.add(1);
  }

  sleep(Math.random() * 0.5 + 0.2);
}
