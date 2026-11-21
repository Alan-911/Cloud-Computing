# One EC2 host running the Compose stack (nginx, api, PostgreSQL) from the
# published GHCR image. Docker's data, including the PostgreSQL volume, lives on
# a separate encrypted EBS volume, so replacing the instance keeps the data.

data "aws_ec2_instance_type" "selected" {
  instance_type = var.instance_type
}

locals {
  arch = contains(data.aws_ec2_instance_type.selected.supported_architectures, "arm64") ? "arm64" : "x86_64"
}

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-${local.arch}"
}

resource "aws_ebs_volume" "data" {
  availability_zone = aws_subnet.public.availability_zone
  size              = var.data_volume_gb
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "${var.name}-${var.environment}-data" }
}

resource "aws_instance" "app" {
  ami                    = nonsensitive(data.aws_ssm_parameter.al2023_ami.value)
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]
  iam_instance_profile   = aws_iam_instance_profile.app.name

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # containers cannot reach instance credentials
    http_endpoint               = "enabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repo_url       = "https://github.com/${var.github_repository}.git"
    app_ref        = var.app_ref
    image_tag      = var.image_tag
    data_volume_id = aws_ebs_volume.data.id
    arch           = local.arch
  })
  user_data_replace_on_change = true

  # The AMI parameter moves when Amazon publishes a new image. Pick that up
  # deliberately (`terraform apply -replace=aws_instance.app`), not on every plan.
  lifecycle {
    ignore_changes = [ami]
  }

  tags = { Name = "${var.name}-${var.environment}-app" }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.app.id
}

resource "aws_eip" "app" {
  domain   = "vpc"
  instance = aws_instance.app.id
  tags     = { Name = "${var.name}-${var.environment}-app" }

  depends_on = [aws_internet_gateway.main]
}
