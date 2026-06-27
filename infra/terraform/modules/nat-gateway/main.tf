locals {
  name_prefix = "goa-${var.environment}"

  common_tags = merge(
    var.tags,
    {
      Environment = var.environment
      ManagedBy   = "terraform"
      Module      = "nat-gateway"
      Project     = "goa"
    }
  )
}

resource "aws_eip" "nat" {
  count = length(var.public_subnet_ids)

  domain = "vpc"

  tags = merge(
    local.common_tags,
    {
      Name = format("%s-nat-eip-%s", local.name_prefix, count.index + 1)
    }
  )
}

resource "aws_nat_gateway" "this" {
  count = length(var.public_subnet_ids)

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = var.public_subnet_ids[count.index]

  tags = merge(
    local.common_tags,
    {
      Name = format("%s-nat-%s", local.name_prefix, count.index + 1)
    }
  )
}

resource "aws_route" "private_app_default" {
  count = length(var.private_app_route_table_ids)

  route_table_id         = var.private_app_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[count.index].id
}

resource "aws_route" "private_data_default" {
  count = length(var.private_data_route_table_ids)

  route_table_id         = var.private_data_route_table_ids[count.index]
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[count.index].id
}
