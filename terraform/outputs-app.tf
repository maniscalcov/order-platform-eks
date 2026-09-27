# Separate file from outputs.tf so adding this doesn't require editing a
# file you already have open / mid-diff. Terraform merges every .tf file
# in the directory automatically - this doesn't need to be combined with
# the existing file for `terraform output` to show all of them together.

output "orders_table_name" {
  value = aws_dynamodb_table.orders.name
}

output "inventory_table_name" {
  value = aws_dynamodb_table.inventory.name
}

output "inventory_queue_url" {
  description = "Set this as INVENTORY_QUEUE_URL in order-api's and inventory-worker's ConfigMaps."
  value       = aws_sqs_queue.inventory.id
}

output "payment_queue_url" {
  description = "Set this as PAYMENT_QUEUE_URL in inventory-worker's and payment-worker's ConfigMaps."
  value       = aws_sqs_queue.payment.id
}

output "order_api_role_arn" {
  description = "Already matches the annotation in k8s/order-api/serviceaccount.yaml if ACCOUNT_ID was replaced correctly."
  value       = aws_iam_role.order_api.arn
}

output "inventory_worker_role_arn" {
  value = aws_iam_role.inventory_worker.arn
}

output "payment_worker_role_arn" {
  value = aws_iam_role.payment_worker.arn
}
