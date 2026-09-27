# ---------------------------------------------------------------------------
# Inventory queue
#
# order-api -> inventory-worker hand-off. A message here is exactly one
# InventoryReservationMessage (see order-api/app/models.py and
# inventory-worker/app/models.py - the shape is duplicated between the two
# services on purpose, see the comment at the top of the latter).
# ---------------------------------------------------------------------------
resource "aws_sqs_queue" "inventory_dlq" {
  name = "${var.project_name}-inventory-dlq"

  # Max allowed retention. A message only lands here after repeated
  # processing failures, so give yourself real time to notice a DLQ isn't
  # empty and go investigate before it ages out.
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Project = var.project_name
  }
}

resource "aws_sqs_queue" "inventory" {
  name = "${var.project_name}-inventory"

  # inventory-worker's reserve/release logic is a handful of DynamoDB
  # calls - a few hundred ms in practice. 30s leaves large margin without
  # letting a genuinely stuck message sit invisible for long.
  visibility_timeout_seconds = 30
  message_retention_seconds  = 345600 # 4 days (SQS default)

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.inventory_dlq.arn
    # Retried this many times before moving to the DLQ. 3 survives a
    # transient DynamoDB throttle without masking a genuinely broken
    # message for too long.
    maxReceiveCount = 3
  })

  tags = {
    Project = var.project_name
  }
}

# ---------------------------------------------------------------------------
# Payment queue
#
# inventory-worker -> payment-worker hand-off, sent only after a successful
# reservation. payment-worker is a pure consumer here - nothing publishes
# downstream of it (see the note in its IAM policy in app-iam.tf).
# ---------------------------------------------------------------------------
resource "aws_sqs_queue" "payment_dlq" {
  name                      = "${var.project_name}-payment-dlq"
  message_retention_seconds = 1209600

  tags = {
    Project = var.project_name
  }
}

resource "aws_sqs_queue" "payment" {
  name = "${var.project_name}-payment"

  # Same reasoning as the inventory queue's timeout, with a little extra
  # margin: the simulated gateway in payment_gateway.py sleeps up to 300ms
  # per call, and a real processor could run slower still.
  visibility_timeout_seconds = 30
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.payment_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Project = var.project_name
  }
}
