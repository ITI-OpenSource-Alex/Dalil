terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.100"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }

    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  skip_credentials_validation = var.aws_skip_credentials_validation
  skip_metadata_api_check     = var.aws_skip_metadata_api_check
  skip_requesting_account_id  = var.aws_skip_requesting_account_id
  skip_region_validation      = var.aws_skip_region_validation

  default_tags {
    tags = local.common_tags
  }
}
