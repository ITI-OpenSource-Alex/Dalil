resource "aws_ecr_repository" "this" {
  for_each = var.repositories

  name = "${var.name_prefix}-${each.value}"

  # GOA-022 (N7): CI tags images by commit SHA, which is immutable by
  # definition. IMMUTABLE turns an accidental overwrite of an already-deployed
  # tag into a push failure instead of a silent substitution, so a task
  # definition pinned to a SHA can never start resolving to different bytes.
  #
  # Consequence: re-running a deploy for a SHA that is already in ECR would
  # fail the push, so deploy-template.yml checks for the tag first and skips
  # build/push when it exists.
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.tags, {
    Name    = "${var.name_prefix}-${each.value}"
    Service = each.value
    Module  = "ecr"
  })
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each = aws_ecr_repository.this

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Retain the most recent ${var.image_retention_count} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.image_retention_count
      }
      action = { type = "expire" }
    }]
  })
}
