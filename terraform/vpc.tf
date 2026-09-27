data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  cluster_name = "${var.project_name}-eks"
  azs          = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # /20 per subnet out of a /16 leaves plenty of IPs. The VPC CNI assigns
  # a real VPC IP to every pod, so subnets that feel generous for EC2 can
  # run dry surprisingly fast on Kubernetes.
  public_subnets  = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  private_subnets = [for i, az in local.azs : cidrsubnet(var.vpc_cidr, 4, i + 8)]
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "${var.project_name}-vpc"
  cidr = var.vpc_cidr

  azs             = local.azs
  public_subnets  = local.public_subnets
  private_subnets = local.private_subnets

  enable_nat_gateway = true

  # Single NAT gateway: one AZ of failure risk, but roughly $32/mo instead
  # of $32 per AZ. For a portfolio project that gets destroyed between
  # sessions this is the right trade. Flip to false for a "production"
  # story in your write-up.
  single_nat_gateway = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  # These tags are what let the AWS Load Balancer Controller auto-discover
  # where to place ALBs. Getting them wrong is the single most common cause
  # of an Ingress that provisions nothing and logs nothing useful.
  public_subnet_tags = {
    "kubernetes.io/role/elb" = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = "1"
    # Needed later if you add Cluster Autoscaler (Karpenter does not use these).
    "karpenter.sh/discovery" = local.cluster_name
  }
}
