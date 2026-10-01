# Chaos experiment 2: order-api loses DynamoDB write access

Simulates one of the most common real outages: a bad IAM change removes a
service's permission to write to its database.

## Why IAM and not Chaos Mesh DNSChaos / NetworkChaos

- **DNSChaos would likely do nothing.** boto3 keeps pooled keep-alive HTTPS
  connections to DynamoDB; under steady load they never go idle, so order-api
  never re-resolves the hostname and never hits the injected DNS failure.
- **A network partition produces hangs, not errors.** Requests stall on
  botocore's 60s connect/read timeouts and retries instead of failing fast.
- **HTTPChaos is invisible to the SLI.** It aborts requests in a proxy before
  they reach the app, but the availability SLI comes from order-api's own
  middleware, so the errors would never be counted (an observability blind
  spot worth knowing about).
- **An explicit IAM Deny fails fast and is realistic.** IAM is evaluated on
  every API call, so the Deny applies to the pod's existing IRSA session
  within seconds. `put_order()` raises AccessDeniedException -> order-api
  returns 500 -> the availability SLI drops. An explicit Deny overrides every
  Allow (and the permissions boundary).

## Hypothesis (written before the run)

1. Within seconds of injection, 100% of POST /orders return 500.
2. `OrdersAvailabilityBudgetBurnCritical` (14.4x on 1h AND 5m, `for: 2m`)
   goes PENDING, then FIRING, within ~3-4 minutes.
3. `OrdersAvailabilityBudgetBurnWarning` (3x on 1d AND 2h, `for: 15m`) goes
   PENDING and fires ~15 min later, even after recovery (slow-burn tier).
4. No order is written during the fault, so 0 orders get stuck in
   PENDING / INVENTORY_RESERVED; workers and queues are unaffected.
5. Within seconds of removing the Deny, POST /orders returns 201 again;
   the critical alert resolves once the 5m window is clean.

## Run (one command per line; note every timestamp)

```powershell
# 0. Load: 25 min of ~20 orders/s (Job spec is immutable -> delete the old Job first)
kubectl delete job k6-load -n order-platform --ignore-not-found
kubectl apply -f load-test\k6-job.yaml; Get-Date -Format "HH:mm:ss"

# 1. After 5 clean minutes: INJECT
aws iam put-role-policy --role-name order-platform-order-api --policy-name chaos-deny-dynamodb-write --policy-document file://chaos/deny-dynamodb-write.json; Get-Date -Format "HH:mm:ss"
aws iam list-role-policies --role-name order-platform-order-api

# 2. After 8 minutes: REVERT (do not skip - this policy is outside Terraform)
aws iam delete-role-policy --role-name order-platform-order-api --policy-name chaos-deny-dynamodb-write; Get-Date -Format "HH:mm:ss"
aws iam list-role-policies --role-name order-platform-order-api
```

## Evidence to capture

- Grafana: availability SLI + requests/sec by status (201 -> 500 -> 201).
- Prometheus /alerts: Critical PENDING -> FIRING -> resolved (timestamps).
- order-api logs during the fault: `kubectl logs deploy/order-api -n order-platform --tail=20`
- DynamoDB scan: 0 stuck orders created since the run started.
