import json
import os

import boto3


def load_writing_runtime_secrets() -> None:
    """Load the Writing JSON secret before the database engine is imported in Lambda."""
    secret_arn = os.getenv("WRITING_SECRET_ARN", "").strip()
    if not secret_arn:
        return
    client = boto3.client(
        "secretsmanager",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )
    response = client.get_secret_value(SecretId=secret_arn)
    values = json.loads(response.get("SecretString") or "{}")
    for key, value in values.items():
        if value is not None and not os.getenv(key):
            os.environ[key] = str(value)
