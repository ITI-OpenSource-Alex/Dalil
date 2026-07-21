# -----------------------------------------------------------------------------
# GOA-074: GitHub Branch Protection Rules
# NOTE: Commented out — requires a GitHub token and a paid GitHub plan for
# branch protection on private repos. Uncomment and run terraform apply
# once the GitHub token is configured via TF_VAR_github_token.
# -----------------------------------------------------------------------------

# resource "github_branch_protection" "main" {
#   repository_id                   = var.github_repo
#   pattern                         = "main"
#   enforce_admins                  = true
#   require_conversation_resolution = true
#   allows_deletions                = false
#   allows_force_pushes             = false
#
#   required_pull_request_reviews {
#     dismiss_stale_reviews           = true
#     required_approving_review_count = 1
#     require_code_owner_reviews      = false
#   }
#
#   required_status_checks {
#     strict   = true
#     contexts = ["test-services"]
#   }
# }

# resource "github_branch_protection" "dev" {
#   repository_id                   = var.github_repo
#   pattern                         = "dev"
#   enforce_admins                  = true
#   require_conversation_resolution = true
#   allows_deletions                = false
#   allows_force_pushes             = false
#
#   required_pull_request_reviews {
#     dismiss_stale_reviews           = true
#     required_approving_review_count = 1
#   }
#
#   required_status_checks {
#     strict   = true
#     contexts = ["test-services"]
#   }
# }
