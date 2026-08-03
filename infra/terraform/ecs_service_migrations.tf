# Preserve the seven ECS services and task definition histories while ownership
# moves from the original all-in-one ecs-cluster module to the parameterised
# ecs-service module introduced by GOA-071.

moved {
  from = module.ecs_cluster.aws_ecs_task_definition.this["gateway"]
  to   = module.ecs_service["gateway"].aws_ecs_task_definition.this
}

moved {
  from = module.ecs_cluster.aws_ecs_task_definition.this["user"]
  to   = module.ecs_service["user"].aws_ecs_task_definition.this
}

moved {
  from = module.ecs_cluster.aws_ecs_task_definition.this["orchestration"]
  to   = module.ecs_service["orchestration"].aws_ecs_task_definition.this
}

moved {
  from = module.ecs_cluster.aws_ecs_task_definition.this["speaking"]
  to   = module.ecs_service["speaking"].aws_ecs_task_definition.this
}

moved {
  from = module.ecs_cluster.aws_ecs_task_definition.this["writing"]
  to   = module.ecs_service["writing"].aws_ecs_task_definition.this
}

moved {
  from = module.ecs_cluster.aws_ecs_task_definition.this["rag"]
  to   = module.ecs_service["rag"].aws_ecs_task_definition.this
}

moved {
  from = module.ecs_cluster.aws_ecs_task_definition.this["exam"]
  to   = module.ecs_service["exam"].aws_ecs_task_definition.this
}

moved {
  from = module.ecs_cluster.aws_ecs_service.this["gateway"]
  to   = module.ecs_service["gateway"].aws_ecs_service.this
}

moved {
  from = module.ecs_cluster.aws_ecs_service.this["user"]
  to   = module.ecs_service["user"].aws_ecs_service.this
}

moved {
  from = module.ecs_cluster.aws_ecs_service.this["orchestration"]
  to   = module.ecs_service["orchestration"].aws_ecs_service.this
}

moved {
  from = module.ecs_cluster.aws_ecs_service.this["speaking"]
  to   = module.ecs_service["speaking"].aws_ecs_service.this
}

moved {
  from = module.ecs_cluster.aws_ecs_service.this["writing"]
  to   = module.ecs_service["writing"].aws_ecs_service.this
}

moved {
  from = module.ecs_cluster.aws_ecs_service.this["rag"]
  to   = module.ecs_service["rag"].aws_ecs_service.this
}

moved {
  from = module.ecs_cluster.aws_ecs_service.this["exam"]
  to   = module.ecs_service["exam"].aws_ecs_service.this
}
