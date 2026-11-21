# Runbook — infrastructure (Terraform, AWS)

All AWS resources for the app are defined in `infrastructure/terraform/`. Nothing is
created by hand, and `terraform destroy` removes everything it created.

```
infrastructure/terraform/
  bootstrap/   once per account: S3 state bucket, GitHub OIDC provider, read-only plan role
  app/         the environment: VPC, subnet, security group, EC2 host, data volume, EIP,
               instance role (SSM), GitHub deploy role, optional budget alert
```

## What gets built

```
Internet ──:80──▶ Elastic IP ──▶ EC2 t4g.small (Amazon Linux 2023, arm64)
                                 ├─ docker compose: nginx ─▶ api ─▶ postgres
                                 ├─ root volume 20 GB (gp3, encrypted)
                                 └─ /data  10 GB EBS (gp3, encrypted): Docker data + app .env
VPC 10.20.0.0/16, one public subnet, no NAT gateway.
Inbound: TCP 80 only (SSH only if admin_ssh_cidrs is set). Outbound: TCP 443 only.
Shell access: SSM Session Manager.  Deploys: SSM Run Command from GitHub Actions (OIDC).
```

Design choices:
- **No SSH, no stored keys.** Shell access goes through Session Manager. Deploys assume a role through GitHub OIDC that may only run commands on this one instance, and only from the `production` environment.
- **IMDSv2 only, hop limit 1.** Containers can't reach the instance's credentials.
- **The data volume is separate.** PostgreSQL data and the generated `.env` live on `/data`, so replacing the instance (new AMI, changed user data) keeps the data. It's only formatted if it's blank.
- **Secrets stay out of Terraform state.** The database password is generated on the host at first boot.
- **One AZ, one host.** This is the cost floor for a portfolio environment. High availability and replicas come with Kubernetes in Phase 06 and scaling in Phase 09.

Estimated cost (us-east-1 on-demand, AWS Price List API, 2026-11-21):

| Item | Monthly |
|---|---|
| t4g.small instance | $12.26 |
| 30 GB gp3 | $2.40 |
| Public IPv4 address | $3.65 |
| State bucket | < $0.01 |
| **Total** | **≈ $18.31** |

A t4g.micro brings the total to about $12.18, but it's tight for PostgreSQL. Set
`budget_alert_email` to get emails at 80% of actual and 100% of forecast spend.

## Before you start: don't use root credentials

Use an IAM Identity Center user or an IAM role with administrator access, signed
in with `aws login` or `aws sso login`, not the account's root access keys. Delete
root access keys once you have an administrator identity.

## 1. Bootstrap (once per account)

```bash
cd infrastructure/terraform/bootstrap
terraform init
terraform plan            # expect: 11 to add
terraform apply
terraform output -raw app_backend_config > ../app/backend.hcl
```

The bootstrap stack keeps local state (`bootstrap/terraform.tfstate`, git-ignored).
Back it up; it holds no secrets.

Repository variables (Settings → Secrets and variables → Actions → Variables) turn on
the `terraform plan` job in the Infrastructure workflow:

| Variable | Value |
|---|---|
| `AWS_PLAN_ROLE_ARN` | `terraform output -raw terraform_plan_role_arn` |
| `TF_STATE_BUCKET` | `terraform output -raw state_bucket` |

## 2. Create the environment

The first boot checks out `app_ref` and runs `image_tag`, so both must already be
published (defaults: `v1.4.0` / `1.4.0`).

```bash
cd infrastructure/terraform/app
cp terraform.tfvars.example terraform.tfvars   # optional overrides
terraform init -backend-config=backend.hcl
terraform plan            # expect: 18 to add (19 with a budget)
terraform apply
terraform output
```

First boot takes about 3–5 minutes. Then check it:

```bash
curl -s "$(terraform output -raw app_url)/api/health"
aws ssm start-session --target "$(terraform output -raw instance_id)"   # shell, no SSH
sudo tail -n 50 /var/log/cloud-init-output.log                          # first-boot log
```

Production environment variables (Settings → Environments → `production`) for the
Deploy workflow:

| Variable | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `terraform output -raw deploy_role_arn` |
| `EC2_INSTANCE_ID` | `terraform output -raw instance_id` |
| `APP_URL` | `terraform output -raw app_url` |

## Change the infrastructure

1. Edit the `.tf` files and open a pull request. The Infrastructure workflow runs
   `fmt`, `validate` and `tflint`, plus a read-only `plan` once the variables above are set.
   Trivy (in Security) checks the Terraform for misconfiguration.
2. After merge, run `terraform plan` and then `terraform apply` from an administrator
   workstation. CI never applies.

Replace the host, for example to pick up a newer Amazon Linux AMI (data is kept):

```bash
terraform apply -replace=aws_instance.app
```

## Destroy

```bash
scripts/db-backup.sh                         # on the host, if the data matters
cd infrastructure/terraform/app && terraform destroy
cd ../bootstrap && terraform destroy         # only when retiring the project; the
                                             # bucket must be emptied first
```

`terraform destroy` on the app stack deletes the data volume. Take a backup first.

## Accepted scanner findings

| Finding | Severity | Decision |
|---|---|---|
| AWS-0104: egress to 0.0.0.0/0 | Critical | Accepted. Outbound is limited to TCP 443, but the destinations (package mirrors, GHCR, SSM) are CDNs without stable IP ranges. Suppressed inline with this reason. |
| AWS-0132: state bucket without a customer-managed KMS key | High | Accepted. The state holds no secrets; SSE-S3 encrypts at rest. Suppressed inline. |
| AWS-0178: no VPC flow logs | Medium | Deferred to Phase 08 (cost against value for one host). |
| AWS-0027: EBS without a customer-managed key | Low | Accepted. Volumes are encrypted with the AWS-managed key. |
| AWS-0089: no access logging on the state bucket | Low | Accepted. CloudTrail records bucket API calls. |
