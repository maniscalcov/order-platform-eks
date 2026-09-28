variable "region" {
  description = "AWS region for all resources."
  type        = string
  default     = "us-east-2"
}

variable "project_name" {
  description = "Short name used to prefix resources."
  type        = string
  default     = "order-platform"
}

variable "cluster_version" {
  description = "EKS control plane version. Pin this explicitly."
  type        = string
  default     = "1.35"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3. EKS requires at least 2 AZs."
  }
}

variable "node_instance_types" {
  description = <<-EOT
    Instance types for the managed node group. t3.medium is fine for
    Phases 1-3. Note that t3 is burstable: under sustained load testing
    you can exhaust CPU credits and see latency that has nothing to do
    with your app. Switch to m5.large for load-test sessions if that bites.
  EOT
  type        = list(string)
  default     = ["t3.medium"]
}

variable "node_desired_size" {
  description = "Starting number of worker nodes."
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of worker nodes."
  type        = number
  default     = 2
}

variable "node_max_size" {
  description = <<-EOT
    Maximum number of worker nodes. Headroom matters: once Prometheus,
    Grafana, ArgoCD and KEDA land in Phase 4, two t3.medium nodes get
    tight and you will see pods go Pending.
  EOT
  type        = number
  default     = 4
}

variable "admin_principal_arns" {
  description = <<-EOT
    IAM principal ARNs granted cluster-admin via EKS access entries.
    Put your own IAM user/role ARN here so kubectl works after apply.
    Leave empty to rely solely on the cluster creator's implicit access.
  EOT
  type        = list(string)
  default     = []
}

variable "iam_permissions_boundary_arn" {
  description = <<-EOT
    ARN of the order-platform-boundary policy. Every IAM role Terraform
    creates (EKS cluster role, node role, IRSA roles) gets this attached.
    Required if the terraform-cli-iam user policy is in place, since that
    policy refuses to create a role without it.
  EOT
  type        = string
  default     = null
}

variable "public_api_access_cidrs" {
  description = <<-EOT
    CIDRs allowed to reach the public EKS API endpoint. Defaults to
    open, which is convenient but not great. Narrow this to your own
    IP (e.g. ["203.0.113.4/32"]) once you have things working.
  EOT
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
