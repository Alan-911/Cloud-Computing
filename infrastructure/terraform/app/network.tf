# A dedicated VPC with one public subnet. No NAT gateway (it would cost more than
# the instance); the instance reaches the internet through its Elastic IP.

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "${var.name}-${var.environment}" }
}

# Strip all rules from the VPC's default security group so nothing can use it by accident.
resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.name}-${var.environment}-default-unused" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.name}-${var.environment}" }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = false # the instance gets an Elastic IP instead
  tags                    = { Name = "${var.name}-${var.environment}-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.name}-${var.environment}-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# --- Security group ----------------------------------------------------------------

resource "aws_security_group" "web" {
  name        = "${var.name}-${var.environment}-web"
  description = "HTTP from the internet to nginx; optional SSH from admin CIDRs only"
  vpc_id      = aws_vpc.main.id
  tags        = { Name = "${var.name}-${var.environment}-web" }
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.web.id
  description       = "HTTP to nginx (the only published container port)"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  for_each = toset(var.admin_ssh_cidrs)

  security_group_id = aws_security_group.web.id
  description       = "SSH from an administrator network"
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

# Outbound HTTPS only: dnf repositories, GitHub and GHCR, the Compose plugin
# download, and the SSM agent. DNS (VPC resolver) and NTP (169.254.169.123) are not
# filtered by security groups, so nothing else needs to leave the host.
# The destinations are CDNs without stable IP ranges, so the CIDR stays open.
#trivy:ignore:AWS-0104
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.web.id
  description       = "HTTPS for OS updates, GitHub/GHCR, and the SSM agent"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
