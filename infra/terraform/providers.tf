terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }


    # NOTE: GitHub provider requires a paid org plan for branch protection.
    # Uncomment when the org is upgraded.
    # github = {
    #   source  = "integrations/github"
    #   version = "~> 6.0"
    # }

    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Offline planning is explicit. Normal staging/production runs use the AWS
  # SDK credential chain (environment, shared config, SSO, or instance role).
  access_key                  = var.aws_offline_mode ? "mock_access_key" : null
  secret_key                  = var.aws_offline_mode ? "mock_secret_key" : null
  skip_credentials_validation = var.aws_offline_mode
  skip_metadata_api_check     = var.aws_offline_mode
  skip_requesting_account_id  = var.aws_offline_mode
  skip_region_validation      = var.aws_offline_mode
  s3_use_path_style           = var.aws_offline_mode
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  access_key                  = var.aws_offline_mode ? "mock_access_key" : null
  secret_key                  = var.aws_offline_mode ? "mock_secret_key" : null
  skip_credentials_validation = var.aws_offline_mode
  skip_metadata_api_check     = var.aws_offline_mode
  skip_requesting_account_id  = var.aws_offline_mode
  skip_region_validation      = var.aws_offline_mode
  s3_use_path_style           = var.aws_offline_mode
}

# NOTE: GitHub provider requires a paid org plan for branch protection.
# Uncomment when the org is upgraded.
# provider "github" {
#   owner = var.github_org
#   token = var.github_token
# }
