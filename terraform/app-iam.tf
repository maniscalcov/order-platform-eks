# ---------------------------------------------------------------------------
# App roles: order-api, inventory-worker, payment-worker
#
# Same IRSA pattern as ebs_csi/alb_controller in irsa.tf - reuses
# local.oidc_provider_arn and local.oidc_provider_url defined there, since
# this is the same root module. Each role below is scoped to exactly what
# its own service does. No role here can do anything outside its own job:
# order-api can't read the inventory table, payment-worker can't publish
# to any queue. That asymmetry is deliberate and worth pointing to directly
# if asked about least privilege in an interview.
#
# The :sub value in each trust policy must exactly match
# "system:serviceaccount:<namespace>:<service-account-name>" - these three
# match the namespace in k8s/namespace.yaml and the ServiceAccount names in
# k8s/<service>/serviceaccount.yaml. If a pod gets
# "AccessDenied"/"not authorized" despite the role existing, the :sub
# mismatch here is the first thing to check.
# ---------------------------------------------------------------------------

# =============================================================================
# order-api
# =============================================================================

data "aws_iam_policy_document" "order_api_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:order-platform:order-api"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "order_api" {
  name                 = "${var.project_name}-order-api"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.order_api_assume.json
}

data "aws_iam_policy_document" "order_api_permissions" {
  # Writes new orders, reads them back for GET /orders/{id}.
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }

  # Publishes to the inventory queue only. Never receives, never touches
  # the payment queue - it doesn't know the payment queue exists.
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.inventory.arn]
  }
}

resource "aws_iam_policy" "order_api" {
  name   = "${var.project_name}-order-api"
  policy = data.aws_iam_policy_document.order_api_permissions.json
}

resource "aws_iam_role_policy_attachment" "order_api" {
  role       = aws_iam_role.order_api.name
  policy_arn = aws_iam_policy.order_api.arn
}

# =============================================================================
# inventory-worker
#
# The widest of the three roles, because it's the only service that both
# consumes and produces - see the module docstring in
# inventory-worker/app/db.py.
# =============================================================================

data "aws_iam_policy_document" "inventory_worker_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:order-platform:inventory-worker"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "inventory_worker" {
  name                 = "${var.project_name}-inventory-worker"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.inventory_worker_assume.json
}

data "aws_iam_policy_document" "inventory_worker_permissions" {
  # Status transitions only (update_order_status in db.py) - never PutItem,
  # never GetItem. It doesn't need to read an order to update its status.
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }

  # reserve_item and release_item are both conditional UpdateItem calls.
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.inventory.arn]
  }

  # Consumes from the inventory queue.
  statement {
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.inventory.arn]
  }

  # Hands off to payment-worker on a successful reservation.
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.payment.arn]
  }
}

resource "aws_iam_policy" "inventory_worker" {
  name   = "${var.project_name}-inventory-worker"
  policy = data.aws_iam_policy_document.inventory_worker_permissions.json
}

resource "aws_iam_role_policy_attachment" "inventory_worker" {
  role       = aws_iam_role.inventory_worker.name
  policy_arn = aws_iam_policy.inventory_worker.arn
}

# =============================================================================
# payment-worker
#
# The narrowest of the three. Terminal consumer in the saga - it reads one
# table and drains one queue, nothing else.
# =============================================================================

data "aws_iam_policy_document" "payment_worker_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:order-platform:payment-worker"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "payment_worker" {
  name                 = "${var.project_name}-payment-worker"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.payment_worker_assume.json
}

data "aws_iam_policy_document" "payment_worker_permissions" {
  # get_order_status (idempotency check) + update_order_status_if_current.
  statement {
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.orders.arn]
  }

  # Consumes from the payment queue.
  statement {
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.payment.arn]
  }

  # Deliberately NO sqs:SendMessage statement anywhere in this policy.
  # Nothing comes after payment-worker in the saga, so it has no ability
  # to publish to any queue at all - not a missing feature, a boundary.
}

resource "aws_iam_policy" "payment_worker" {
  name   = "${var.project_name}-payment-worker"
  policy = data.aws_iam_policy_document.payment_worker_permissions.json
}

resource "aws_iam_role_policy_attachment" "payment_worker" {
  role       = aws_iam_role.payment_worker.name
  policy_arn = aws_iam_policy.payment_worker.arn
}
