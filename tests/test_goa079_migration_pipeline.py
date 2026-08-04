from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_terraform_provisions_dedicated_migration_task_definitions():
    migration_tf = (ROOT / "infra/terraform/ecs_migration_tasks.tf").read_text()
    locals_tf = (ROOT / "infra/terraform/locals.tf").read_text()

    assert 'resource "aws_ecs_task_definition" "migration"' in migration_tf
    assert 'family                   = "${local.name_prefix}-${each.key}-migration"' in migration_tf
    assert "aws_iam_role.ecs_migration_task" in migration_tf
    assert "No SQS, S3, SNS, or external API permissions are attached." in migration_tf

    for service in (
        "gateway",
        "user",
        "orchestration",
        "speaking",
        "writing",
        "rag",
        "exam",
        "ingestion",
    ):
        assert f"{service} " in locals_tf or f"{service}=" in locals_tf


def test_deploy_template_runs_migrations_before_service_deploy():
    workflow = (ROOT / ".github/workflows/deploy-template.yml").read_text()

    migration_step = workflow.index("Run database migrations and wait for completion")
    deploy_step = workflow.index("Deploy task definition and wait for stability")

    assert migration_step < deploy_step
    assert "aws ecs run-task" in workflow
    assert "aws ecs wait tasks-stopped" in workflow
    assert "${ECS_SERVICE}-migration" in workflow
    assert "Migration task completed successfully before service deployment." in workflow


def test_migrate_only_entrypoints_exist_for_services_without_cli_migrations():
    expected_files = [
        "services/orchestration/app/migrate.py",
        "services/rag/app/migrate.py",
        "services/exam/app/migrate.py",
        "services/ingestion/app/migrate.py",
        "services/ingestion/app/core/migrations.py",
        "services/ingestion/app/migrations/001_initial_schema.sql",
        "services/ingestion/app/migrations/rollback/001_initial_schema_down.sql",
        "services/gateway/migrations/001_noop.sql",
        "services/gateway/migrations/rollback/001_noop_down.sql",
    ]

    for relative_path in expected_files:
        assert (ROOT / relative_path).exists(), relative_path


def test_user_production_image_has_a_compiled_typeorm_migration_command():
    package_json = (ROOT / "services/user/package.json").read_text()

    assert "migration:run:prod" in package_json
    assert "dist/database/data-source.js" in package_json
