import json
import boto3
import structlog
from botocore.exceptions import ClientError
import os
logger = structlog.get_logger(__name__)
# Usually set in docker-compose, e.g. http://localstack:4566
S3_ENDPOINT = os.getenv("S3_ENDPOINT", "http://localstack:4566")
ENV = os.getenv("APP_ENV", "dev")
BUCKET_NAME = f"goa-ingestion-reports-{ENV}"


def get_s3_client():
    return boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id='test',
        aws_secret_access_key='test',
        region_name='us-east-1'
    )


def ensure_bucket_exists(s3_client):
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            s3_client.create_bucket(Bucket=BUCKET_NAME)
            logger.info("created_s3_bucket", bucket=BUCKET_NAME)


def upload_report_to_s3(run_id: str, report_data: dict):
    """Uploads the rich per-source JSON report to S3."""
    s3 = get_s3_client()
    ensure_bucket_exists(s3)
    
    key = f"reports/{run_id}.json"
    
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=key,
            Body=json.dumps(report_data, indent=2),
            ContentType="application/json"
        )
        logger.info("uploaded_report_to_s3", key=key)
    except Exception as e:
        logger.error("s3_upload_failed", key=key, error=str(e))

        