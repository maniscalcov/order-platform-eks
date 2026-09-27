// k6 load test for order-api.
//
// Purpose: generate enough sustained traffic to (a) push order-api pods
// past the HPA's 60% CPU target so you can watch them scale, and (b) build
// a real backlog on the SQS queues so the workers have something to chew
// through.
//
// Run it:
//   kubectl port-forward -n order-platform svc/order-api 8080:80
//   k6 run load-test/order-api-load.js
//
// Watch it work, in three other terminals:
//   kubectl get hpa -n order-platform -w
//   kubectl get pods -n order-platform -w
//   kubectl top pods -n order-platform

import http from "k6/http";
import { check, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";

// Custom metrics beyond what k6 gives you by default. ordersCreated is the
// one to compare against DynamoDB afterward - if the table has fewer rows
// than this counter, something dropped orders.
const ordersCreated = new Counter("orders_created");
const orderCreateFailed = new Rate("order_create_failed");
const createLatency = new Trend("order_create_latency", true);

// These SKUs must exist in the order-platform-inventory table with enough
// quantity_available to survive the run, or inventory-worker will mark
// every order INVENTORY_FAILED and you'll be load-testing the failure path
// by accident. Seed generously: this test can easily create 10k+ orders.
const SKUS = [
  "SKU-WIDGET-001",
  "SKU-WIDGET-002",
  "SKU-GADGET-010",
  "SKU-GADGET-011",
  "SKU-DOODAD-100",
];

export const options = {
  // Staged ramp rather than a flat load: the HPA reacts to *sustained*
  // utilization (30s stabilization window), so a brief spike proves
  // nothing. Each plateau is long enough for scaling to actually happen
  // and settle.
  stages: [
    { duration: "1m", target: 10 },   // warm-up: pods start, connections open
    { duration: "2m", target: 50 },   // should cross the 60% CPU target
    { duration: "3m", target: 100 },  // sustained - watch replicas climb
    { duration: "2m", target: 150 },  // push toward maxReplicas: 10
    { duration: "3m", target: 150 },  // hold: does latency stay flat once scaled?
    { duration: "2m", target: 0 },    // ramp down - then watch the 5m
                                      //   scale-down window before pods go
  ],

  // A run that violates these exits non-zero, which is what makes this
  // usable in CI later rather than something you eyeball.
  thresholds: {
    http_req_failed: ["rate<0.01"],              // <1% errors
    http_req_duration: ["p(95)<500", "p(99)<1500"],
    order_create_failed: ["rate<0.01"],
  },
};

function randomOrder() {
  const itemCount = Math.floor(Math.random() * 3) + 1; // 1-3 line items
  const items = [];
  const used = new Set();

  for (let i = 0; i < itemCount; i++) {
    // Don't repeat a SKU within one order - the API would accept it, but
    // it makes reserved-quantity math harder to reason about when you're
    // reconciling the inventory table afterward.
    let sku;
    do {
      sku = SKUS[Math.floor(Math.random() * SKUS.length)];
    } while (used.has(sku));
    used.add(sku);

    items.push({
      sku: sku,
      quantity: Math.floor(Math.random() * 3) + 1,
      unit_price_cents: (Math.floor(Math.random() * 90) + 10) * 100, // $10-$99
    });
  }

  return {
    // Spread across many customers so nothing accidentally serializes on
    // a single partition key.
    customer_id: `cust-${Math.floor(Math.random() * 10000)}`,
    items: items,
  };
}

export default function () {
  const payload = JSON.stringify(randomOrder());
  const params = {
    headers: { "Content-Type": "application/json" },
    tags: { name: "POST /orders" }, // groups metrics by endpoint
  };

  const res = http.post(`${BASE_URL}/orders`, payload, params);

  const ok = check(res, {
    "status is 201": (r) => r.status === 201,
    "returned an order_id": (r) => {
      try {
        return typeof r.json("order_id") === "string";
      } catch (e) {
        return false;
      }
    },
    "status is PENDING": (r) => {
      try {
        return r.json("status") === "PENDING";
      } catch (e) {
        return false;
      }
    },
  });

  createLatency.add(res.timings.duration);
  orderCreateFailed.add(!ok);
  if (ok) ordersCreated.add(1);

  // Jittered think time. A fixed sleep makes every VU fire in lockstep,
  // which produces an unrealistic sawtooth on the queue and on CPU.
  sleep(Math.random() * 0.5 + 0.2);
}

export function teardown() {
  console.log(
    "\nRun finished. Worth checking now:\n" +
      "  - kubectl get hpa -n order-platform      (did it scale, and how far?)\n" +
      "  - SQS console: messages in flight / DLQ depth\n" +
      "  - Scan DynamoDB for status=PENDING rows: anything stuck means an\n" +
      "    order was written but its queue publish failed.\n" +
      "  - Compare orders_created above against the row count in the table.\n"
  );
}
