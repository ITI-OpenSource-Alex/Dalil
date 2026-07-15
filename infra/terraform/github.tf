terraform {
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

# The GitHub repository name (e.g., "goa-backend")
variable "github_repository_name" {
  type    = string
  default = "goa"
}

# Branch Protection for main (Production)
resource "github_branch_protection" "main" {
  repository_id                   = var.github_repository_name
  pattern                         = "main"
  enforce_admins                  = true
  require_conversation_resolution = true
  allows_deletions                = false
  allows_force_pushes             = false

  required_pull_request_reviews {
    dismiss_stale_reviews           = true
    required_approving_review_count = 1
    require_code_owner_reviews      = false
  }

  required_status_checks {
    strict   = true
    contexts = ["CI"] # Ensure your PR test action is named "CI"
  }
}

# Branch Protection for develop (Staging)
resource "github_branch_protection" "develop" {
  repository_id                   = var.github_repository_name
  pattern                         = "develop"
  enforce_admins                  = true
  require_conversation_resolution = true
  allows_deletions                = false
  allows_force_pushes             = false

  required_pull_request_reviews {
    dismiss_stale_reviews           = true
    required_approving_review_count = 1
  }

  required_status_checks {
    strict   = true
    contexts = ["CI"] # Ensure your PR test action is named "CI"
  }
}