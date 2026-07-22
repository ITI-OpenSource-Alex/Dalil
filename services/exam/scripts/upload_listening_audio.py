"""Upload validated Listening section audio to S3 or LocalStack."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


KEY_PATTERN = re.compile(
    r"^exam-audio/(?P<book>IELTS-\d+)/(?P<test>\d+)/"
    r"section(?P<section>[1-4])\.mp3$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--endpoint-url")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="BOOK/TEST",
        help="Only upload a test such as IELTS-15/1; may be repeated",
    )
    parser.add_argument("--create-bucket", action="store_true")
    return parser.parse_args()


def discover_audio(
    source_root: Path,
    includes: set[str],
) -> list[tuple[str, Path]]:
    groups: dict[str, dict[int, tuple[str, Path]]] = defaultdict(dict)
    for audio_file in source_root.glob("exam-audio/IELTS-*/*/section*.mp3"):
        key = audio_file.relative_to(source_root).as_posix()
        match = KEY_PATTERN.fullmatch(key)
        if match is None:
            continue

        group = f"{match.group('book')}/{match.group('test')}"
        if includes and group not in includes:
            continue
        section = int(match.group("section"))
        groups[group][section] = (key, audio_file)

    missing_groups = includes.difference(groups)
    if missing_groups:
        raise ValueError(f"Requested tests not found: {sorted(missing_groups)}")

    discovered: list[tuple[str, Path]] = []
    for group, sections in sorted(groups.items()):
        if set(sections) != {1, 2, 3, 4}:
            raise ValueError(f"{group} does not contain all four sections")
        for section in range(1, 5):
            key, audio_file = sections[section]
            if audio_file.stat().st_size == 0:
                raise ValueError(f"Audio file is empty: {audio_file}")
            discovered.append((key, audio_file))

    if not discovered:
        raise ValueError("No Listening audio files found")
    return discovered


def ensure_bucket(client: object, bucket: str, region: str) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        return
    except ClientError:
        params = {"Bucket": bucket}
        if region != "us-east-1":
            params["CreateBucketConfiguration"] = {"LocationConstraint": region}
        client.create_bucket(**params)


def main() -> None:
    args = parse_args()
    audio_files = discover_audio(args.source_root.resolve(), set(args.include))
    client = boto3.client(
        "s3",
        region_name=args.region,
        endpoint_url=args.endpoint_url,
    )
    if args.create_bucket:
        ensure_bucket(client, args.bucket, args.region)

    for key, audio_file in audio_files:
        client.upload_file(
            str(audio_file),
            args.bucket,
            key,
            ExtraArgs={"ContentType": "audio/mpeg"},
        )
        print(f"uploaded s3://{args.bucket}/{key}")

    print(f"uploaded {len(audio_files)} files")


if __name__ == "__main__":
    main()
