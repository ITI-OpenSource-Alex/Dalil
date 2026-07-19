"""Safely replay failed asynchronous S3 invocations after configuration recovery."""

import argparse
import json
import os
from typing import Any

import boto3


def request_payload(message_body: str) -> dict[str, Any]:
    envelope = json.loads(message_body)
    payload = envelope.get("requestPayload")
    if not isinstance(payload, dict) or not isinstance(payload.get("Records"), list):
        raise ValueError("Failure message does not contain an S3 requestPayload")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay CV processor Lambda failure-destination messages"
    )
    parser.add_argument("--queue-url", required=True)
    parser.add_argument("--function-name", required=True)
    parser.add_argument("--max-messages", type=int, default=10)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Invoke Lambda and delete successful messages; default is a dry run",
    )
    args = parser.parse_args()
    if not 1 <= args.max_messages <= 1000:
        parser.error("--max-messages must be between 1 and 1000")

    client_kwargs = {"region_name": os.getenv("AWS_REGION", "eu-west-1")}
    endpoint_url = os.getenv("AWS_ENDPOINT_URL")
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    sqs = boto3.client("sqs", **client_kwargs)
    lambda_client = boto3.client("lambda", **client_kwargs)

    inspected = replayed = 0
    while inspected < args.max_messages:
        response = sqs.receive_message(
            QueueUrl=args.queue_url,
            MaxNumberOfMessages=min(10, args.max_messages - inspected),
            WaitTimeSeconds=1,
        )
        messages = response.get("Messages", [])
        if not messages:
            break
        for message in messages:
            payload = request_payload(message["Body"])
            inspected += 1
            if not args.execute:
                continue
            invocation = lambda_client.invoke(
                FunctionName=args.function_name,
                InvocationType="Event",
                Payload=json.dumps(payload).encode("utf-8"),
            )
            if invocation.get("StatusCode") != 202:
                raise RuntimeError(
                    f"Lambda rejected replay with status {invocation.get('StatusCode')}"
                )
            sqs.delete_message(
                QueueUrl=args.queue_url,
                ReceiptHandle=message["ReceiptHandle"],
            )
            replayed += 1

    mode = "executed" if args.execute else "dry-run"
    print(json.dumps({"mode": mode, "inspected": inspected, "replayed": replayed}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
