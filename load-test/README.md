# Load testing

Two scripts, meant to be run in this order.

## 1. smoke-test.js — does the saga work at all?

Creates one order and polls until it reaches a terminal state. Run this
first, every time. If the smoke test doesn't pass, the load test will just
generate noise.

```
kubectl port-forward -n order-platform svc/order-api 8080:80
k6 run load-test/smoke-test.js
```

A healthy run walks `PENDING` → `INVENTORY_RESERVED` → `PAYMENT_COMPLETED`
in well under a minute. `PAYMENT_FAILED` is also a pass — the simulated
gateway declines about 10% of charges on purpose, and a decline still
means every service in the chain did its job.

## 2. order-api-load.js — does it scale?

```
k6 run load-test/order-api-load.js
```

13 minutes, ramping 10 → 150 virtual users and back down. Watch in
separate terminals:

```
kubectl get hpa -n order-platform -w
kubectl get pods -n order-platform -w
kubectl top pods -n order-platform
```

## Installing k6

```
winget install k6 --source winget
```

(or `choco install k6`, or grab the binary from grafana.com/docs/k6)

## Before running

Seed the `order-platform-inventory` table with the five SKUs listed at the
top of `order-api-load.js`, each with a generous `quantity_available` — a
full run can create 10,000+ orders, and if stock runs out mid-test every
subsequent order goes `INVENTORY_FAILED` and you end up load-testing the
rollback path instead of the happy one.

## What to actually look for

The HPA scaling up is the obvious thing, but the interesting findings are
usually elsewhere:

- **Does p95 latency come back down after pods are added?** If it stays
  high, the bottleneck isn't order-api — likely DynamoDB throttling.
- **Does the queue drain after the ramp-down, or keep growing?** A queue
  that never catches up is the argument for KEDA in one chart.
- **Any DLQ messages?** Those are real bugs worth reading.
- **Any orders stuck in `PENDING`?** That's the write-succeeded-but-publish-
  failed gap that `main.py` deliberately leaves open.
- **`orders_created` in the k6 summary vs. row count in DynamoDB.** They
  should match exactly.

Screenshot the HPA scaling and the Grafana dashboards during the run —
that's the portfolio artifact, more than the scripts themselves.
