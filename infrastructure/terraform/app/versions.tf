terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
  }

  # Partial configuration: `terraform init -backend-config=backend.hcl`.
  # The values come from the bootstrap stack's `app_backend_config` output.
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "cloud-native-backend"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = var.github_repository
    }
  }
}
