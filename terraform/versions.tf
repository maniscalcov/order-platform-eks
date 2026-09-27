terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Uncomment once you have created an S3 bucket + DynamoDB lock table
  # for remote state. Local state is fine to start, but move it before
  # you wire up CI/CD.
  #
  # backend "s3" {
  #   bucket         = "vinny-tfstate-<unique>"
  #   key            = "eks-order-platform/terraform.tfstate"
  #   region         = "us-east-2"
  #   dynamodb_table = "terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
    }
  }
}
