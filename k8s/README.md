# Kubernetes manifests

Apply in this order (namespace first - everything else is namespaced):

```
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/order-api/
kubectl apply -f k8s/inventory-worker/
kubectl apply -f k8s/payment-worker/
```

Verify:

```
kubectl get pods -n order-platform
kubectl logs -n order-platform -l app=inventory-worker --tail=50
kubectl get hpa -n order-platform
```

## Before you apply

Every `<ACCOUNT_ID>` placeholder must be replaced, and each ECR image
needs a real tag. Three IAM roles must exist with trust policies naming
their matching service account (see the comments in each
`serviceaccount.yaml` for the exact permissions each one needs).

The `order-platform-inventory` DynamoDB table also doesn't exist yet -
Phase 1 only created the orders table. Add it (partition key `sku`,
attribute `quantity_available`) and seed a few SKUs.

## Why the workers have no Service and no HPA

Nothing in the cluster calls a worker, so there's nothing for a Service to
route - they pull their own work from SQS. That also means a CPU-based HPA
is the wrong instrument: a worker sitting in a 20-second long-poll with a
thousand messages queued behind it shows almost no CPU. The HPA would see
an idle pod and scale *down* exactly when the backlog is worst.

The right signal is queue depth
(`ApproximateNumberOfMessagesVisible`), which needs KEDA:

```
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda -n keda --create-namespace
```

Then a `ScaledObject` per worker with an `aws-sqs-queue` trigger. That's a
good Phase 4/5 addition once the basic flow works end to end - and the
reasoning above ("CPU is the wrong metric for a queue consumer") is worth
having ready as an interview answer.

## Worker vs API differences worth knowing

| | order-api | workers |
|---|---|---|
| Service | ClusterIP | none |
| Probes | readiness + liveness | liveness only |
| Autoscaling | HPA on CPU | KEDA on queue depth (later) |
| Grace period | 30s | 60s (long-poll + in-flight batch) |
