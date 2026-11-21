output "app_url" {
  value = "http://${aws_eip.app.public_ip}"
}

output "public_ip" {
  value = aws_eip.app.public_ip
}

output "instance_id" {
  description = "Set as the production environment variable EC2_INSTANCE_ID."
  value       = aws_instance.app.id
}

output "deploy_role_arn" {
  description = "Set as the production environment variable AWS_DEPLOY_ROLE_ARN."
  value       = aws_iam_role.deploy.arn
}

output "data_volume_id" {
  value = aws_ebs_volume.data.id
}

output "shell" {
  description = "Open a shell on the host without SSH (needs the Session Manager plugin)."
  value       = "aws ssm start-session --region ${var.region} --target ${aws_instance.app.id}"
}

output "architecture" {
  value = local.arch
}
