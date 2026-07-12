import re
import zipfile
from pathlib import PurePath
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.config import MAX_CV_SIZE_BYTES, READ_CHUNK_SIZE


MIME_TO_EXTENSION = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}
SAFE_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def validate_user_id(user_id: str) -> None:
    if not SAFE_USER_ID.fullmatch(user_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="userId contains unsupported characters",
        )


def safe_original_filename(filename: str | None) -> str:
    normalized = (filename or "").replace("\\", "/")
    basename = PurePath(normalized).name
    if not basename or basename in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="A valid filename is required",
        )
    return basename[:255]


async def validate_upload(upload: UploadFile) -> tuple[str, str]:
    extension = MIME_TO_EXTENSION.get(upload.content_type or "")
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOC, and DOCX files are supported",
        )

    original_filename = safe_original_filename(upload.filename)
    supplied_extension = PurePath(original_filename).suffix.lower().lstrip(".")
    if supplied_extension != extension:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The filename extension does not match the declared media type",
        )

    total = 0
    header = b""
    while chunk := await upload.read(READ_CHUNK_SIZE):
        total += len(chunk)
        if total > MAX_CV_SIZE_BYTES:
            await upload.seek(0)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="CV files must be 10 MB or smaller",
            )
        if len(header) < 8:
            header = (header + chunk)[:8]

    await upload.seek(0)
    if total == 0 or not _signature_matches(upload, extension, header):
        await upload.seek(0)
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file content does not match the declared media type",
        )

    await upload.seek(0)
    return extension, original_filename


def _signature_matches(upload: UploadFile, extension: str, header: bytes) -> bool:
    if extension == "pdf":
        return header.startswith(b"%PDF-")
    if extension == "doc":
        return header.startswith(OLE_SIGNATURE)

    try:
        with zipfile.ZipFile(upload.file) as archive:
            names = set(archive.namelist())
            return "[Content_Types].xml" in names and any(
                name.startswith("word/") for name in names
            )
    except (OSError, zipfile.BadZipFile):
        return False
    finally:
        upload.file.seek(0)


def make_s3_key(user_id: str, extension: str) -> str:
    return f"cvs/{user_id}/{uuid4()}.{extension}"


def upload_to_s3(s3_client, upload: UploadFile, bucket: str, key: str) -> None:
    upload.file.seek(0)
    s3_client.upload_fileobj(
        upload.file,
        bucket,
        key,
        ExtraArgs={"ContentType": upload.content_type},
    )


def delete_from_s3(s3_client, bucket: str, key: str) -> None:
    s3_client.delete_object(Bucket=bucket, Key=key)
