import boto3

from app.config import Settings, get_settings
from app.database import SessionLocal


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _aws_client(service_name: str, settings: Settings):
    return boto3.client(
        service_name,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        endpoint_url=settings.aws_endpoint_url,
    )


def get_s3_client():
    return _aws_client("s3", get_settings())


def get_sqs_client():
    return _aws_client("sqs", get_settings())
