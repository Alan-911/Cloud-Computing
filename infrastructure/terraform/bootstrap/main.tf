# One-time bootstrap, applied with local state by an administrator:
#
#   * S3 bucket for the app stack's remote state (versioned, encrypted, private,
#     TLS-only; locking uses S3 lock files, so no DynamoDB table is needed)
#   * GitHub Actions OIDC identity provider (keyless CI access to AWS)
#   * a read-only role CI assumes to run `terraform plan` on pull requests
#
# Keep the resulting terraform.tfstate somewhere safe; it is small and holds no secrets.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project   = "cloud-native-backend"
      Stack     = "bootstrap"
      ManagedBy = "terraform"
      Repo      = var.github_repository
    }
  }
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "github_oidc_subject_prefix" {
  description = <<-EOT
    Prefix of the `sub` claim in this repository's GitHub OIDC tokens. The repo
    uses immutable subject claims, which embed the owner and repository IDs, so a
    renamed or re-created repository with the same name cannot assume the roles.
    Read it with: gh api repos/OWNER/REPO/actions/oidc/customization/sub
  EOT
  type        = string
  default     = "repo:Alan-911@136555079/Cloud-Computing@1400158294"
}

variable "github_repository" {
  description = "owner/name of the repository (used for tags)."
  type        = string
  default     = "Alan-911/Cloud-Computing"
}

data "aws_caller_identity" "current" {}

locals {
  state_bucket = "cbe-tfstate-${data.aws_caller_identity.current.account_id}-${var.region}"
}

# --- Remote state bucket -------------------------------------------------------

resource "aws_s3_bucket" "state" {
  bucket = local.state_bucket
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-S3 rather than a customer-managed KMS key: the state holds no secrets (the
# database password is generated on the host), so a CMK would add cost (~$1/month)
# and key administration without protecting anything sensitive.
#trivy:ignore:AWS-0132
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

data "aws_iam_policy_document" "state_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.state.arn,
      "${aws_s3_bucket.state.arn}/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket     = aws_s3_bucket.state.id
  policy     = data.aws_iam_policy_document.state_tls_only.json
  depends_on = [aws_s3_bucket_public_access_block.state]
}

# --- GitHub Actions OIDC ---------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Read-only role for `terraform plan` on pull requests. It can read the account
# and the state, but cannot change anything (plans run with -lock=false).
data "aws_iam_policy_document" "plan_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "${var.github_oidc_subject_prefix}:pull_request",
        "${var.github_oidc_subject_prefix}:ref:refs/heads/*",
      ]
    }
  }
}

resource "aws_iam_role" "terraform_plan" {
  name                 = "cbe-github-terraform-plan"
  assume_role_policy   = data.aws_iam_policy_document.plan_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read_only" {
  role       = aws_iam_role.terraform_plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "aws_iam_policy_document" "plan_state_read" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.state.arn}/*"]
  }
}

resource "aws_iam_role_policy" "plan_state_read" {
  name   = "read-terraform-state"
  role   = aws_iam_role.terraform_plan.id
  policy = data.aws_iam_policy_document.plan_state_read.json
}

# --- Outputs ------------------------------------------------------------------------

output "state_bucket" {
  value = aws_s3_bucket.state.bucket
}

output "github_oidc_provider_arn" {
  value = aws_iam_openid_connect_provider.github.arn
}

output "terraform_plan_role_arn" {
  description = "Set as the repository variable AWS_PLAN_ROLE_ARN."
  value       = aws_iam_role.terraform_plan.arn
}

output "app_backend_config" {
  description = "Contents for infrastructure/terraform/app/backend.hcl."
  value       = <<-EOT
    bucket       = "${aws_s3_bucket.state.bucket}"
    key          = "app/production.tfstate"
    region       = "${var.region}"
    encrypt      = true
    use_lockfile = true
  EOT
}
