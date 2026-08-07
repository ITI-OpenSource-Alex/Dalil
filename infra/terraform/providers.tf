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

    # Packages the GOA-046 weekly cost-report Lambda from source.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
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

  # GOA-046. Tagging every resource from the provider rather than per-module is
  # what makes the Cost Explorer split trustworthy: a module that forgets to
  # thread `tags` through still produces attributable spend. Resource-level tags
  # override these, so a service-owned resource keeps its own Service value.
  default_tags {
    tags = local.common_tags
  }

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

  default_tags {
    tags = local.common_tags
  }

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
