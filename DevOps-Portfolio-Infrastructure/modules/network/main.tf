# Declare the data source
data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  min_ha = min(length(data.aws_availability_zones.available.names), var.ha)
  total  = local.min_ha <= 1 ? 1 : local.min_ha
}


####### VPC part ####### 

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidrs
  enable_dns_hostnames = true
  tags = {
    Name = "${var.name_prefix}-VPC"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags = {
    Name = "${var.name_prefix}-IGW"
  }
}

resource "aws_route_table" "internet" {
  vpc_id = aws_vpc.this.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = {
    Name = "${var.name_prefix}-RTB"
  }
}

resource "aws_subnet" "this" {
  count = local.total

  vpc_id                  = aws_vpc.this.id
  map_public_ip_on_launch = true
  cidr_block              = cidrsubnet(var.vpc_cidrs, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  tags = {
    Name = "${var.name_prefix}-SUBNET-${count.index}"
  }
}

resource "aws_route_table_association" "this" {
  count          = local.total
  subnet_id      = aws_subnet.this[count.index].id
  route_table_id = aws_route_table.internet.id
}