from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_deploy_has_manual_environment_gate_and_no_rebuild():
    workflow = (ROOT / ".github/workflows/deploy-production.yml").read_text()

    assert "environment:" in workflow
    assert "name: production" in workflow
    assert "docker/build-push-action" not in workflow
    assert "Promote staging image SHAs and deploy ECS services" in workflow


def test_production_deploy_promotes_exact_staging_images():
    workflow = (ROOT / ".github/workflows/deploy-production.yml").read_text()

    assert "goa-staging-${service}" in workflow
    assert "goa-production-${service}" in workflow
    assert "aws ecr batch-get-image" in workflow
    assert "aws ecr put-image" in workflow
    assert "staging_digest" in workflow
    assert "production_image=" in workflow
    assert "Promoted images" in workflow


def test_production_deploy_rolls_back_after_failed_smoke_tests():
    workflow = (ROOT / ".github/workflows/deploy-production.yml").read_text()

    deploy_step = workflow.index("Promote staging image SHAs and deploy ECS services")
    smoke_step = workflow.index("Run production smoke tests")
    rollback_step = workflow.index("Roll back ECS task definitions after failed smoke tests")

    assert deploy_step < smoke_step < rollback_step
    assert "previous-task-definitions.tsv" in workflow
    assert "if: failure() && steps.deploy-production.outcome == 'success'" in workflow
    assert "aws ecs update-service" in workflow
    assert "aws ecs wait services-stable" in workflow


def test_production_deploy_reports_status_and_slack_notifications():
    workflow = (ROOT / ".github/workflows/deploy-production.yml").read_text()

    assert "deploy/production" in workflow
    assert "gh api -X POST" in workflow
    assert "SLACK_WEBHOOK_URL" in workflow
    assert "Production deploy and smoke tests passed" in workflow


def test_dev_promotion_runs_staging_e2e_and_creates_main_pr_summary():
    workflow = (ROOT / ".github/workflows/promote-to-production.yml").read_text()

    assert "branches:" in workflow
    assert "- dev" in workflow
    assert "vars.STAGING_INFRA_READY == 'true'" in workflow
    assert "PLAYWRIGHT_BASE_URL" in workflow
    assert "npm run test:e2e" in workflow
    assert "Wait for changed services to finish staging deploy" in workflow
    assert "github.sha" in workflow
    assert "aws ecs wait services-stable" in workflow
    assert "gh pr create" in workflow
    assert "--base main" in workflow
    assert "--head dev" in workflow
    assert "Performance metrics from the last hour" in workflow
    assert "git diff --stat origin/main...HEAD" in workflow


def test_frontend_e2e_can_target_real_staging_url():
    config = (ROOT / "services/frontend/playwright.config.ts").read_text()

    assert "PLAYWRIGHT_BASE_URL" in config
    assert "useExternalBaseURL" in config
    assert "webServer: useExternalBaseURL" in config


def test_terraform_allows_production_role_to_read_staging_promotion_inputs():
    oidc = (ROOT / "infra/terraform/oidc.tf").read_text()

    assert "ReadStagingImagesForPromotion" in oidc
    assert "ReadStagingServicesForPromotion" in oidc
    assert 'Resource = local.github_deploy_ecr_repository_arns["staging"]' in oidc
    assert 'Resource = local.github_deploy_ecs_service_arns["staging"]' in oidc
    assert "cloudwatch:GetMetricStatistics" in oidc


def test_required_manual_github_environment_setup_is_documented():
    doc = (ROOT / "docs/deployment/GOA-080-production-promotion.md").read_text()

    assert "Required reviewers" in doc
    assert "production" in doc
    assert "Gate test" in doc
    assert "SHA test" in doc
    assert "Rollback test" in doc
