terraform {
  backend "local" {
    path = "terraform.tfstate"
  }

  # Switch to this backend after running bootstrap.sh with real AWS credentials.
  #
  # backend "s3" {
  #   bucket         = "goa-staging-terraform-state"
  #   key            = "foundation/terraform.tfstate"
  #   region         = "eu-west-1"
  #   dynamodb_table = "goa-staging-terraform-locks"
  #   encrypt        = true
  # }
}
