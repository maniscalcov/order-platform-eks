module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = local.cluster_name
  cluster_version = var.cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Public endpoint so you can run kubectl from your laptop without a
  # bastion. Narrow public_api_access_cidrs to your own IP once working.
  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = var.public_api_access_cidrs
  cluster_endpoint_private_access      = true

  # Creates the OIDC provider that IRSA depends on. Same trust model as
  # your GitHub Actions OIDC role, with Kubernetes as the identity provider.
  enable_irsa = true

  # Applies to the cluster role and node role this module creates. Required
  # once the terraform-cli-iam user policy is attached — that policy denies
  # iam:CreateRole unless this boundary is present.
  iam_role_permissions_boundary = var.iam_permissions_boundary_arn

  # Access entries are the modern replacement for the aws-auth ConfigMap.
  # API_AND_CONFIG_MAP keeps the old path working for any Helm chart that
  # still expects it.
  authentication_mode                      = "API_AND_CONFIG_MAP"
  enable_cluster_creator_admin_permissions = true

  access_entries = {
    for idx, arn in var.admin_principal_arns : "admin-${idx}" => {
      principal_arn = arn
      policy_associations = {
        admin = {
          policy_arn = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = {
            type = "cluster"
          }
        }
      }
    }
  }

  cluster_addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni = {
      before_compute              = true
      most_recent                 = true
      resolve_conflicts_on_create = "OVERWRITE"
      resolve_conflicts_on_update = "OVERWRITE"
    }
    eks-pod-identity-agent = {}
    # EKS community add-on. Installed by Terraform so every fresh cluster has
    # it: without it the order-api HPA reads "<unknown>" and never scales.
    metrics-server = {}
    aws-ebs-csi-driver = {
      # Prometheus and Grafana want PersistentVolumes. Without this addon
      # their PVCs sit Pending forever and the failure mode is not obvious.
      service_account_role_arn    = aws_iam_role.ebs_csi.arn
      resolve_conflicts_on_create = "OVERWRITE"
      resolve_conflicts_on_update = "OVERWRITE"
    }
  }

  # Control plane logging. Cheap, and genuinely useful when debugging
  # why an IRSA-authenticated pod is getting AccessDenied.
  cluster_enabled_log_types = ["api", "audit", "authenticator"]

  # The EKS metrics-server add-on listens on 10251 (kubelet owns 10250).
  # The module's default node SG rules don't open it, so the API server's
  # calls to metrics-server time out -> APIService FailedDiscoveryCheck.
  node_security_group_additional_rules = {
    ingress_cluster_metrics_server = {
      description                   = "Cluster API to metrics-server"
      protocol                      = "tcp"
      from_port                     = 10251
      to_port                       = 10251
      type                          = "ingress"
      source_cluster_security_group = true
    }
  }

  eks_managed_node_group_defaults = {
    ami_type                      = "AL2023_x86_64_STANDARD"
    iam_role_permissions_boundary = var.iam_permissions_boundary_arn

    # The module's default node-group role name doesn't include your
    # project prefix, which means it can never match the
    # "role/order-platform-*" restriction in your IAM policy — every
    # CreateRole call fails with an implicit deny regardless of the
    # boundary being correct. Forcing the prefix here fixes that.
    iam_role_name            = "${var.project_name}-node-group"
    iam_role_use_name_prefix = true
  }

  eks_managed_node_groups = {
    default = {
      instance_types = var.node_instance_types
      capacity_type  = "ON_DEMAND"

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      # Chaos Mesh (Phase 5) and node-exporter both want real node access,
      # which is why this is a managed node group rather than Fargate.
      labels = {
        workload = "general"
      }
    }
  }
}
