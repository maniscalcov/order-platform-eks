# ---------------------------------------------------------------------------
# GitHub Actions -> AWS via OIDC (no stored access keys)
#
# Each workflow run gets a short-lived token signed by GitHub. AWS checks the
# token's "sub" claim (which repo + branch is asking) against this role's
# trust policy and hands back ~1h credentials. Same trust model as IRSA, with
# GitHub as the identity provider instead of the EKS cluster.
# ---------------------------------------------------------------------------

# The provider already exists in this account (created for the Cloud Resume
# Challenge). An account can only have one provider per URL, so reference it
# rather than create it.
data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

locals {
  github_repo = "maniscalcov/order-platform-eks"
  ecr_repos   = ["order-api", "inventory-worker", "payment-worker"]
}

data "aws_iam_policy_document" "github_actions_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [data.aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Only pushes to main in this one repo can assume the role. Pull requests
    # (including from forks) still build and scan, but never get AWS creds.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${local.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name                 = "${var.project_name}-github-actions"
  assume_role_policy   = data.aws_iam_policy_document.github_actions_assume.json
  permissions_boundary = var.iam_permissions_boundary_arn
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_actions_ecr" {
  # GetAuthorizationToken does not support resource-level permissions.
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # Push/pull limited to this project's three repositories.
  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
    ]
    resources = [
      for r in local.ecr_repos :
      "arn:aws:ecr:${var.region}:${data.aws_caller_identity.current.account_id}:repository/${r}"
    ]
  }
}

resource "aws_iam_role_policy" "github_actions_ecr" {
  name   = "ecr-push"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_ecr.json
}

output "github_actions_role_arn" {
  description = "Paste into the AWS_ROLE_ARN repo variable in GitHub"
  value       = aws_iam_role.github_actions.arn
}
