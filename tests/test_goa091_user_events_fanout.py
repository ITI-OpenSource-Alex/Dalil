from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUBSCRIBERS = [
    "rag",
    "orchestration",
    "exam",
    "speaking",
    "writing",
    "notification",
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_terraform_replaces_bare_user_events_queue_with_sns_fanout():
    locals_tf = read("infra/terraform/locals.tf")
    stateful_tf = read("infra/terraform/stateful.tf")

    assert 'resource "aws_sns_topic" "user_events"' in stateful_tf
    assert 'name = "${local.name_prefix}-user-events"' in stateful_tf
    assert 'raw_message_delivery = true' in stateful_tf
    assert "user_events = {" not in locals_tf

    for subscriber in SUBSCRIBERS:
        key = f"user_events_{subscriber}"
        queue_name = f'${{local.name_prefix}}-user-events-{subscriber}'
        assert key in locals_tf
        assert queue_name in locals_tf
        assert f'"{key}"' in locals_tf


def test_terraform_subscriber_queues_have_dlqs_and_sns_delivery_policy():
    module_main = read("infra/terraform/modules/sqs/main.tf")
    module_vars = read("infra/terraform/modules/sqs/variables.tf")
    stateful_tf = read("infra/terraform/stateful.tf")

    assert 'resource "aws_sqs_queue" "dlq"' in module_main
    assert 'maxReceiveCount     = each.value.max_receive_count' in module_main
    assert "visibility_timeout_seconds = 30" in read("infra/terraform/locals.tf")
    assert "aws_sns_topic_subscription" in stateful_tf
    assert "aws_sqs_queue_policy" in stateful_tf
    assert '"sns.amazonaws.com"' in stateful_tf

    assert '"user_events_rag"' in module_vars
    assert "user-events subscriber queues" in module_vars


def test_localstack_creates_raw_sns_subscriptions_without_old_queue():
    script = read("infra/localstack/init/20-user-events-resources.sh")

    assert 'TOPIC="user-events"' in script
    assert "RawMessageDelivery=true" in script
    assert "--protocol sqs" in script
    assert "aws:SourceArn" in script
    assert "for queue in \\\n  user-events \\" not in script

    for subscriber in SUBSCRIBERS:
        assert f"user-events-{subscriber}" in script
        assert f"user-events-{subscriber}-dlq" in script or '${queue}-dlq' in script


def test_user_service_publishes_user_events_to_sns_only():
    service = read("services/user/src/users/users.service.ts")
    publish_user_event = service.split("private async publishUserEvent", 1)[1]

    assert "SNSClient" in service
    assert "PublishCommand" in service
    assert "USER_EVENTS_TOPIC_ARN" in publish_user_event
    assert "TopicArn: topicArn" in publish_user_event
    assert "Message: JSON.stringify(event)" in publish_user_event
    assert "this.sqsService.send" not in publish_user_event


def test_rag_defaults_to_dedicated_subscriber_queue():
    config = read("services/rag/app/core/config.py")
    compose = read("docker-compose.yml")

    assert 'SQS_QUEUE_NAME: str = "user-events-rag"' in config
    assert "SQS_QUEUE_NAME=user-events-rag" in compose
    assert "SQS_QUEUE_URL=http://localstack:4566/000000000000/user-events" not in compose
