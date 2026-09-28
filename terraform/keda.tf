# ---------------------------------------------------------------------------
# KEDA operator IRSA role
#
# KEDA scales inventory-worker and payment-worker on SQS queue depth. The
# KEDA operator (not the workers) calls GetQueueAttributes, so it gets its
# own role, scoped to exactly one action on exactly the two work queues.
# It cannot read, send or delete messages.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "keda_assume" {
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
      values   = ["system:serviceaccount:keda:keda-operator"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "keda_operator" {
  name                 = "${var.project_name}-keda-operator"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.keda_assume.json
}

data "aws_iam_policy_document" "keda_operator" {
  statement {
    sid       = "ReadQueueDepthOnly"
    effect    = "Allow"
    actions   = ["sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.inventory.arn, aws_sqs_queue.payment.arn]
  }
}

resource "aws_iam_policy" "keda_operator" {
  name   = "${var.project_name}-keda-operator"
  policy = data.aws_iam_policy_document.keda_operator.json
}

resource "aws_iam_role_policy_attachment" "keda_operator" {
  role       = aws_iam_role.keda_operator.name
  policy_arn = aws_iam_policy.keda_operator.arn
}

output "keda_operator_role_arn" {
  value = aws_iam_role.keda_operator.arn
}