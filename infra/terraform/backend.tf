terraform {
  # Values are supplied by environments/shared.backend.hcl (created by
  # bootstrap.sh). workspace_key_prefix isolates staging and production state.
  backend "s3" {}
}
