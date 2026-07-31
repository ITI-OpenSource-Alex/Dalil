from __future__ import annotations

import json
import logging
from typing import Any

import boto3
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import CVReview, Essay

logger = logging.getLogger(__name__)


def parse_account_deleted_event(message_body: str | dict[str, Any]) -> str | None:
    event = json.loads(message_body) if isinstance(message_body, str) else message_body
    if event.get("Type") == "Notification" and event.get("Message"):
        event = json.loads(event["Message"])
    if event.get("type") != "account.deleted":
        return None
    return event.get("payload", {}).get("userId")


def purge_user_data(db: Session, user_id: str, s3_client: Any | None = None) -> dict[str, int]:
    settings = get_settings()
    s3 = s3_client or boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    deleted_objects = 0
    for prefix in (f"cvs/{user_id}/", f"essays/{user_id}/"):
        continuation_token = None
        while True:
            kwargs = {"Bucket": settings.s3_bucket, "Prefix": prefix}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = s3.list_objects_v2(**kwargs)
            objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
            if objects:
                s3.delete_objects(Bucket=settings.s3_bucket, Delete={"Objects": objects})
                deleted_objects += len(objects)
            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")

    essays_deleted = db.query(Essay).filter(Essay.user_id == user_id).delete(synchronize_session=False)
    cv_reviews_deleted = db.query(CVReview).filter(CVReview.user_id == user_id).delete(synchronize_session=False)
    db.commit()

    logger.info(
        "Purged writing data for deleted account",
        extra={
            "user_id": user_id,
            "essays_deleted": essays_deleted,
            "cv_reviews_deleted": cv_reviews_deleted,
            "s3_objects_deleted": deleted_objects,
        },
    )
    return {
        "essaysDeleted": essays_deleted,
        "cvReviewsDeleted": cv_reviews_deleted,
        "s3ObjectsDeleted": deleted_objects,
    }
