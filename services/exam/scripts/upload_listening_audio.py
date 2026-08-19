"""Upload validated Listening section audio to S3 or LocalStack."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


KEY_PATTERN = re.compile(
    r"^exam-audio/(?P<book>IELTS-\d+)/(?P<test>\d+)/"
    r"section(?P<section>[1-4])\.mp3$"
)
RAW_RECORDING_PATTERN = re.compile(
    r"^Academic (?P<book>\d+) Test (?P<test>\d+)\.mp3$",
    re.IGNORECASE,
)
SILENCE_PATTERN = re.compile(
    r"silence_(?P<event>start|end): (?P<time>\d+(?:\.\d+)?)"
    r"(?: \| silence_duration: (?P<duration>\d+(?:\.\d+)?))?"
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
    parser.add_argument(
        "--split-raw",
        action="store_true",
        help=(
            "Treat source_root as a directory containing files such as "
            "'Academic 15 Test 1.mp3', split them into four sections at the "
            "long inter-section silences, then upload them"
        ),
    )
    return parser.parse_args()


def choose_section_starts(
    duration_seconds: float,
    silences: list[tuple[float, float, float]],
) -> list[float]:
    """Choose the three long-silence ends nearest 25%, 50%, and 75%.

    Cambridge Listening recordings place a long pause between sections. Some
    transitions are one 60-second silence while others are two 30-second
    silences around a spoken instruction, so using only the three longest
    pauses is unreliable. Position plus a 20-second minimum identifies the
    transition consistently while rejecting ordinary answer gaps.
    """
    candidates = [
        end
        for start, end, silence_duration in silences
        if silence_duration >= 20 and 0 < start < end < duration_seconds
    ]
    starts: list[float] = []
    tolerance = duration_seconds * 0.15
    for fraction in (0.25, 0.5, 0.75):
        target = duration_seconds * fraction
        eligible = [
            candidate
            for candidate in candidates
            if abs(candidate - target) <= tolerance
            and (not starts or candidate - starts[-1] >= duration_seconds * 0.15)
        ]
        if not eligible:
            raise ValueError(
                f"Could not locate section transition near {fraction:.0%} "
                f"of a {duration_seconds:.1f}s recording"
            )
        starts.append(min(eligible, key=lambda candidate: abs(candidate - target)))
    return starts


def inspect_recording(audio_file: Path) -> tuple[float, list[tuple[float, float, float]]]:
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_file),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(probe.stdout.strip())
    detection = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(audio_file),
            "-af",
            "silencedetect=noise=-35dB:d=2",
            "-f",
            "null",
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    silences: list[tuple[float, float, float]] = []
    current_start: float | None = None
    for match in SILENCE_PATTERN.finditer(detection.stderr):
        if match.group("event") == "start":
            current_start = float(match.group("time"))
            continue
        if current_start is None or match.group("duration") is None:
            continue
        end = float(match.group("time"))
        silences.append((current_start, end, float(match.group("duration"))))
        current_start = None
    return duration, silences


def split_raw_recordings(recordings_root: Path, output_root: Path) -> None:
    raw_files = sorted(recordings_root.glob("*.mp3"))
    if not raw_files:
        raise ValueError(f"No MP3 recordings found in {recordings_root}")

    for audio_file in raw_files:
        match = RAW_RECORDING_PATTERN.fullmatch(audio_file.name)
        if match is None:
            continue
        duration, silences = inspect_recording(audio_file)
        section_starts = choose_section_starts(duration, silences)
        boundaries = [0.0, *section_starts, duration]
        destination = (
            output_root
            / "exam-audio"
            / f"IELTS-{match.group('book')}"
            / match.group("test")
        )
        destination.mkdir(parents=True, exist_ok=True)

        for section in range(1, 5):
            start = boundaries[section - 1]
            section_duration = boundaries[section] - start
            output_file = destination / f"section{section}.mp3"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{start:.6f}",
                    "-i",
                    str(audio_file),
                    "-t",
                    f"{section_duration:.6f}",
                    "-c",
                    "copy",
                    str(output_file),
                ],
                check=True,
            )
        print(
            f"split {audio_file.name} at "
            + ", ".join(f"{value:.1f}s" for value in section_starts)
        )


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
    source_root = args.source_root.resolve()
    with tempfile.TemporaryDirectory(prefix="goa-listening-audio-") as temp_dir:
        if args.split_raw:
            prepared_root = Path(temp_dir)
            split_raw_recordings(source_root, prepared_root)
            source_root = prepared_root

        audio_files = discover_audio(source_root, set(args.include))
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
