data "aws_caller_identity" "current" {}

locals {
  oidc_provider_arn = module.eks.oidc_provider_arn

  # module.eks.oidc_provider is the issuer URL minus the https:// prefix,
  # which is the form the trust policy condition keys expect.
  oidc_provider_url = module.eks.oidc_provider
}

# ---------------------------------------------------------------------------
# Reusable IRSA trust policy.
#
# The :sub condition is the important line. It scopes the role to exactly one
# namespace + service account. Without it, ANY pod in the cluster that mounts
# a projected token could assume this role. Wildcarding :sub is the most
# common IRSA mistake and it quietly undoes least privilege.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "ebs_csi_assume" {
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
      values   = ["system:serviceaccount:kube-system:ebs-csi-controller-sa"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ebs_csi" {
  name                 = "${var.project_name}-ebs-csi-irsa"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.ebs_csi_assume.json
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

# ---------------------------------------------------------------------------
# AWS Load Balancer Controller
#
# This is what turns a Kubernetes Ingress into a real ALB. Nothing in the
# cluster is reachable from the internet until this exists.
#
# Its IAM policy is long and AWS publishes it. Do not hand-write it. Download
# the current version and drop it next to these files:
#
#   curl -o alb-controller-policy.json \
#     https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/v2.8.2/docs/install/iam_policy.json
#
# Check the repo for the latest release tag rather than assuming v2.8.2 is
# current when you run this.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "alb_controller_assume" {
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
      values   = ["system:serviceaccount:kube-system:aws-load-balancer-controller"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "alb_controller" {
  name                 = "${var.project_name}-alb-controller-irsa"
  permissions_boundary = var.iam_permissions_boundary_arn
  assume_role_policy   = data.aws_iam_policy_document.alb_controller_assume.json
}

resource "aws_iam_policy" "alb_controller" {
  name   = "${var.project_name}-alb-controller"
  policy = file("${path.module}/alb-controller-policy.json")
}

resource "aws_iam_role_policy_attachment" "alb_controller" {
  role       = aws_iam_role.alb_controller.name
  policy_arn = aws_iam_policy.alb_controller.arn
}

# ---------------------------------------------------------------------------
# App roles (order-api, inventory-worker, payment-worker) come in a later
# phase, once the SQS queues and DynamoDB table actually exist. Writing them
# now means guessing at ARNs that do not exist yet.
# ---------------------------------------------------------------------------
