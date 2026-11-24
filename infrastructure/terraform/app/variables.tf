variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "name" {
  description = "Prefix for resource names."
  type        = string
  default     = "cbe"
}

variable "github_repository" {
  description = "owner/name; cloned onto the host."
  type        = string
  default     = "Alan-911/Cloud-Computing"
}

variable "github_oidc_subject_prefix" {
  description = <<-EOT
    Prefix of the `sub` claim in this repository's GitHub OIDC tokens (immutable
    subject claims embed the owner and repository IDs). Only Deploy jobs whose
    token matches <prefix>:environment:<environment> can assume the deploy role.
    Read it with: gh api repos/OWNER/REPO/actions/oidc/customization/sub
  EOT
  type        = string
  default     = "repo:Alan-911@136555079/Cloud-Computing@1400158294"
}

# --- Network --------------------------------------------------------------------

variable "vpc_cidr" {
  description = "Chosen not to overlap the account's existing 10.0.0.0/16 VPC."
  type        = string
  default     = "10.20.0.0/16"
}

variable "public_subnet_cidr" {
  type    = string
  default = "10.20.1.0/24"
}

variable "admin_ssh_cidrs" {
  description = "CIDRs allowed to SSH (port 22). Empty by default: use SSM Session Manager instead."
  type        = list(string)
  default     = []

  validation {
    condition     = !contains(var.admin_ssh_cidrs, "0.0.0.0/0")
    error_message = "Do not open SSH to the whole internet; use SSM Session Manager."
  }
}

# --- Compute --------------------------------------------------------------------

variable "instance_type" {
  description = "Graviton (arm64) by default; the published image is multi-arch."
  type        = string
  default     = "t4g.small"
}

variable "root_volume_gb" {
  type    = number
  default = 20
}

variable "data_volume_gb" {
  description = "Separate EBS volume for Docker data (PostgreSQL) and the app's .env. Survives instance replacement."
  type        = number
  default     = 10
}

variable "app_ref" {
  description = "Git ref checked out on first boot (later deploys choose their own)."
  type        = string
  default     = "v2.0.0"
}

variable "image_tag" {
  description = "Image tag started on first boot."
  type        = string
  default     = "2.0.0"
}

# --- Cost guard -------------------------------------------------------------------

variable "monthly_budget_usd" {
  type    = number
  default = 20
}

variable "budget_alert_email" {
  description = "If set, AWS Budgets emails here at 80% actual and 100% forecast spend."
  type        = string
  default     = ""
}
