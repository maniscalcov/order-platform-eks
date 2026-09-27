// Smoke test: prove the whole saga works before you bother load testing.
//
// Creates ONE order, then polls GET /orders/{id} until it reaches a
// terminal state. This is what tells you inventory-worker and
// payment-worker are actually consuming - the load test alone only proves
// order-api accepts requests.
//
// Run it first, always:
//   kubectl port-forward -n order-platform svc/order-api 8080:80
//   k6 run load-test/smoke-test.js

import http from "k6/http";
import { check, sleep, fail } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8080";

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    checks: ["rate==1.0"], // every check must pass
  },
};

export default function () {
  // 1. Create the order.
  const payload = JSON.stringify({
    customer_id: "smoke-test-customer",
    items: [{ sku: "SKU-WIDGET-001", quantity: 1, unit_price_cents: 2500 }],
  });

  const createRes = http.post(`${BASE_URL}/orders`, payload, {
    headers: { "Content-Type": "application/json" },
  });

  const created = check(createRes, {
    "order created (201)": (r) => r.status === 201,
    "starts as PENDING": (r) => r.json("status") === "PENDING",
  });

  if (!created) {
    fail(`order creation failed: ${createRes.status} ${createRes.body}`);
  }

  const orderId = createRes.json("order_id");
  console.log(`Created order ${orderId}, polling for completion...`);

  // 2. Poll until it leaves PENDING. Each hop is a separate service
  // picking the message up, so give it room: worst case is a message
  // landing just after a worker started a 20s long-poll.
  let status = "PENDING";
  const maxAttempts = 30;

  for (let i = 0; i < maxAttempts; i++) {
    sleep(2);
    const res = http.get(`${BASE_URL}/orders/${orderId}`);
    if (res.status !== 200) continue;

    status = res.json("status");
    console.log(`  [${i * 2}s] status = ${status}`);

    // PAYMENT_COMPLETED and PAYMENT_FAILED are both fine here - the
    // simulated gateway declines ~10% of charges, and a decline still
    // means the whole pipeline ran correctly end to end.
    if (status === "PAYMENT_COMPLETED" || status === "PAYMENT_FAILED") break;

    // This one is NOT fine in a smoke test: it means the SKU above isn't
    // seeded in the inventory table, or has no stock left.
    if (status === "INVENTORY_FAILED") break;
  }

  check(null, {
    "order left PENDING (workers are consuming)": () => status !== "PENDING",
    "inventory reservation succeeded": () => status !== "INVENTORY_FAILED",
    "reached a payment outcome": () =>
      status === "PAYMENT_COMPLETED" || status === "PAYMENT_FAILED",
  });

  if (status === "PENDING") {
    console.log(
      "\nStill PENDING after 60s. Check, in order:\n" +
        "  kubectl logs -n order-platform -l app=inventory-worker --tail=50\n" +
        "  Is the message sitting in the inventory queue? (SQS console)\n" +
        "  Did order-api's publish fail? (check its logs for the warning)\n"
    );
  } else if (status === "INVENTORY_FAILED") {
    console.log(
      "\nINVENTORY_FAILED: SKU-WIDGET-001 is missing from the\n" +
        "order-platform-inventory table, or quantity_available is 0.\n"
    );
  }
}
