# Creates the eight GOA service databases inside the RDS instance.
#
# Why this file exists
# --------------------
# `terraform apply` provisions the RDS *instance* and nothing more. The RDS
# module has a single aws_db_instance resource and does not even set db_name,
# so the eight service databases were never created by anything. The SQL that
# creates them lived only as a Terraform output, `database_bootstrap_sql`,
# consumed by nothing. Its own description said it was meant to be run "after
# the instance is reachable from a private subnet" -- by hand, by someone who
# knew to go looking for it.
#
# The consequence was that GOA-021's acceptance criterion "RDS PostgreSQL with
# all 8 service databases provisioned" could not be met by applying this
# Terraform, and every service except the gateway would fail on boot against a
# database that did not exist. The gateway is the exception because it uses
# Redis only, which is why it was the one service anybody ever got running.
#
# Why a Fargate task rather than the postgresql provider
# -----------------------------------------------------
# modules/rds/main.tf sets publicly_accessible = false, as GOA-070 requires, so
# the instance is only reachable from inside the VPC. Terraform runs on a
# laptop or a CI runner, which is outside it. The postgresql provider, a
# local-exec psql, and every other "run it from where Terraform runs" approach
# fail on that alone.
#
# A one-off Fargate task runs *in* a private subnet, carrying the same security
# group the services use -- which the RDS security group already trusts via
# allowed_security_group_ids. It needs no bastion host, no VPC peering and no
# public endpoint.
#
# The SQL uses psql meta-commands (\set, \gexec), so it has to be piped into
# psql itself; a driver cannot execute it.
#
# How to run it
# -------------
#   ./db-bootstrap.sh staging
#
# The script is separate on purpose. A local-exec provisioner would have to run
# a multi-line shell script through whatever interpreter Terraform picks, which
# differs between Windows, macOS and CI. bootstrap.sh already established the
# "Terraform declares it, a bash script invokes it" pattern in this repository.
#
# The operation is idempotent: the SQL creates a database only WHERE NOT EXISTS,
# so re-running is safe and is the normal way to add a database later.

resource "aws_cloudwatch_log_group" "db_bootstrap" {
  name              = "/aws/ecs/${local.name_prefix}/db-bootstrap"
  retention_in_days = 30

  tags = merge(local.common_tags, { Service = "db-bootstrap" })
}

resource "aws_ecs_task_definition" "db_bootstrap" {
  family                   = "${local.name_prefix}-db-bootstrap"
  cpu                      = "256"
  memory                   = "512"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = module.iam.ecs_task_execution_role_arn
  task_role_arn            = module.iam.ecs_task_role_arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([{
    name      = "db-bootstrap"
    image     = "postgres:16-alpine"
    essential = true

    environment = [
      { name = "PGHOST", value = module.rds.instance_address },
      { name = "PGPORT", value = tostring(module.rds.instance_port) },
      { name = "PGUSER", value = module.secrets.rds_master_username },
      # Connect to the default maintenance database; CREATE DATABASE cannot run
      # from inside the database being created.
      { name = "PGDATABASE", value = "postgres" },
      { name = "BOOTSTRAP_SQL", value = module.rds.database_bootstrap_sql },
    ]

    # ECS pulls the password out of the JSON secret and injects it as PGPASSWORD,
    # so it is never rendered into Terraform state as an environment value and
    # never appears in `describe-task-definition` output.
    secrets = [{
      name      = "PGPASSWORD"
      valueFrom = "${module.secrets.rds_master_secret_arn}:password::"
    }]

    # printf rather than echo: the SQL contains backslashes (\set, \gexec) and
    # POSIX echo is permitted to interpret them, which would corrupt the script.
    command = [
      "sh", "-c",
      "set -e; printf '%s' \"$BOOTSTRAP_SQL\" | psql --no-psqlrc; echo 'db-bootstrap: databases ensured'; psql --no-psqlrc -Atc 'SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname'"
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.db_bootstrap.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "db-bootstrap"
      }
    }
  }])

  tags = merge(local.common_tags, { Service = "db-bootstrap" })
}

output "db_bootstrap_task_definition_arn" {
  description = "Task definition that creates the 8 service databases. Run it with ./db-bootstrap.sh"
  value       = aws_ecs_task_definition.db_bootstrap.arn
}

output "db_bootstrap_log_group" {
  description = "CloudWatch log group carrying db-bootstrap output, including the resulting database list."
  value       = aws_cloudwatch_log_group.db_bootstrap.name
}

# Consumed by db-bootstrap.sh so the script needs no hardcoded network values.
#
# Emitted as pre-joined strings rather than lists so the script can use
# `terraform output -raw` and needs no jq. jq is not installed as widely as its
# appearance in AWS documentation suggests -- it is absent from the Git Bash
# environment this project is developed in, so a jq dependency here would fail
# on the maintainer's own machine.
output "db_bootstrap_subnets" {
  description = "Comma-separated private subnet IDs for the db-bootstrap task."
  value       = join(",", module.vpc.private_app_subnet_ids)
}

output "db_bootstrap_security_groups" {
  description = "Comma-separated security group IDs for the db-bootstrap task."
  value       = module.security_groups.ecs_services_security_group_id
}

output "db_bootstrap_cluster_name" {
  description = "ECS cluster the db-bootstrap task runs on."
  value       = module.ecs_cluster.cluster_name
}
