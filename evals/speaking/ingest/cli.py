"""Benchmark source ingestion CLI (SPEAK-EVAL-005 / 006).

    # transcribe (cassette by default -- no key, no cost, no network)
    python -m evals.speaking.ingest.cli transcribe \
        --item-id smoke-two-speaker \
        --media evals/speaking/fixtures/two_speaker_part1.wav

    # generate the reviewer page
    python -m evals.speaking.ingest.cli review --item-id smoke-two-speaker

    # after a human has filled in the roles, cut clips and measure
    python -m evals.speaking.ingest.cli clips --item-id smoke-two-speaker \
        --annotation <path>

Live provider calls require BOTH `--live` and
`SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS=true`. Two switches rather than one because
the failure being prevented -- an unattended run quietly spending money, or
re-transcribing a benchmark and changing its reference data -- is not one a
single accidental flag should be able to cause.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evals.providers.base import ProviderError, RequestProfile, media_hash
from evals.providers.cassette import CassetteProvider
from evals.providers.gladia import GladiaProvider, live_providers_allowed
from evals.speaking.ingest import clips as clips_mod
from evals.speaking.ingest import metrics as metrics_mod
from evals.speaking.ingest import normalize as normalize_mod
from evals.speaking.ingest import review_report
from evals.speaking.ingest.roles import (
    RoleAnnotation,
    RoleAnnotationError,
    apply_roles,
    new_annotation,
    validate_annotation,
)

REPO = Path(__file__).resolve().parents[3]
ARTIFACT_ROOT = REPO / "evals" / "speaking" / "artifacts"


def artifact_dir(item_id: str) -> Path:
    return ARTIFACT_ROOT / item_id


def _load_transcript(item_id: str) -> normalize_mod.NormalizedTranscript:
    path = artifact_dir(item_id) / "normalized.json"
    if not path.exists():
        raise SystemExit(f"no normalised transcript for {item_id!r}; run `transcribe` first")

    payload = json.loads(path.read_text(encoding="utf-8"))
    utterances = [
        normalize_mod.Utterance(
            **{**u, "words": [normalize_mod.Word(**w) for w in u.get("words", [])]}
        )
        for u in payload.pop("utterances", [])
    ]
    return normalize_mod.NormalizedTranscript(utterances=utterances, **payload)


def cmd_transcribe(args: argparse.Namespace) -> int:
    media = Path(args.media)
    if not media.exists():
        raise SystemExit(f"media not found: {media}")

    profile = RequestProfile()

    if args.live:
        if not live_providers_allowed():
            raise SystemExit(
                "--live requires SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS=true. Refusing "
                "to make a paid call on one flag."
            )
        provider = CassetteProvider(record_with=GladiaProvider())
        print("provider: gladia (live; result will be recorded to a cassette)")
    else:
        provider = CassetteProvider()
        # The idempotency check the ticket asks for, made visible. Re-running an
        # ingested item reuses the artifact instead of re-transcribing it.
        if provider.has(media, profile):
            print("provider: cassette (replay - this item is already ingested)")
        else:
            print("provider: cassette (no recording found; this will fail)")

    try:
        result = provider.transcribe(media, profile, item_id=args.item_id)
    except ProviderError as exc:
        # A provider failure must not leave a partial canonical source behind.
        # Nothing has been written at this point, and nothing will be.
        print(f"ingestion failed, no artifacts written: {exc}", file=sys.stderr)
        return 1

    out = artifact_dir(args.item_id)
    out.mkdir(parents=True, exist_ok=True)

    raw_path = out / "raw.json"
    raw_path.write_text(
        json.dumps(result.raw, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    transcript = normalize_mod.normalize_gladia(
        result.raw,
        item_id=args.item_id,
        job_id=result.job_id,
        idempotency_key=result.idempotency_key,
        raw_sha256=result.raw_sha256(),
        provider=result.identity.provider,
        api_version=result.identity.api_version,
        request_profile_hash=result.identity.request_profile_hash,
        external_docs_reviewed_at=result.identity.external_docs_reviewed_at,
        audio_duration_s=result.audio_duration_s,
    )

    normalized_path = out / "normalized.json"
    normalized_path.write_text(
        json.dumps(transcript.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    annotation_path = out / "role-annotation.json"
    if not annotation_path.exists():
        new_annotation(transcript).save(annotation_path)

    print(f"  media sha256      {media_hash(media)[:16]}...")
    print(f"  idempotency key   {result.idempotency_key[:16]}...")
    print(f"  raw sha256        {result.raw_sha256()[:16]}...  -> {raw_path.name}")
    print(f"  normalized sha256 {transcript.content_sha256()[:16]}...  -> {normalized_path.name}")
    print(f"  utterances        {len(transcript.utterances)}")
    print(f"  provider speakers {transcript.provider_speakers}  (all roles unresolved)")
    if transcript.quarantine:
        print(f"  QUARANTINED       {len(transcript.quarantine)} problem(s):")
        for problem in transcript.quarantine:
            print(f"    {problem}")
        return 1
    print(f"\n  next: review roles -> {annotation_path}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    transcript = _load_transcript(args.item_id)
    out = artifact_dir(args.item_id) / "role-review.html"
    review_report.write_report(transcript, Path(args.media), out)
    print(f"wrote {out}")
    print("Open it, listen, and assign a role to every speaker.")
    print("Speaker 0 is not automatically the candidate.")
    return 0


def cmd_clips(args: argparse.Namespace) -> int:
    transcript = _load_transcript(args.item_id)
    out = artifact_dir(args.item_id)

    annotation_path = Path(args.annotation) if args.annotation else out / "role-annotation.json"
    annotation = RoleAnnotation.load(annotation_path)

    problems = validate_annotation(annotation, transcript, for_gating=args.gating)
    if problems:
        print(f"annotation is not usable ({len(problems)} problem(s)):", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    if annotation.contaminated:
        print(f"item excluded by reviewer: {annotation.exclusion_reason}")
        return 1

    try:
        annotated = apply_roles(transcript, annotation)
    except RoleAnnotationError as exc:
        print(f"could not apply roles: {exc}", file=sys.stderr)
        return 1

    manifest = clips_mod.build_clips(annotated, Path(args.media), out / "clips")
    manifest.save(out / "clip-manifest.json")

    ground_truth = None
    if args.ground_truth:
        ground_truth = json.loads(Path(args.ground_truth).read_text(encoding="utf-8"))

    measured = metrics_mod.compute_metrics(manifest, annotated, ground_truth)
    (out / "segmentation-metrics.json").write_text(
        json.dumps(measured.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"clips            {len(manifest.clips)}")
    for clip in manifest.clips:
        print(
            f"  {clip.clip_id}  {clip.source_start_s:7.2f}-{clip.source_end_s:7.2f}s  "
            f"({clip.duration_s:5.2f}s, {clip.within_answer_pause_s:.2f}s internal pause)  "
            f"{(clip.sha256 or '')[:12]}"
        )
    print(f"\ncandidate kept   {manifest.total_candidate_duration_s:.2f}s")
    print(f"precision        {measured.candidate_precision:.4f}")
    print(f"recall           {measured.candidate_recall:.4f}")
    print(f"contamination    {measured.contamination_s:.2f}s ({measured.contamination_pct:.2f}%)")
    if measured.word_attribution_accuracy is not None:
        print(f"word attribution {measured.word_attribution_accuracy:.4f}")
    if measured.boundary_mae_s is not None:
        print(f"boundary MAE     {measured.boundary_mae_s:.4f}s")

    if measured.valid:
        print("\nVALID: this item may be scored")
        return 0

    print(f"\nEXCLUDED ({len(measured.exclusion_reasons)} reason(s)):")
    for reason in measured.exclusion_reasons:
        print(f"  {reason}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="speaking-ingest", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    transcribe = sub.add_parser("transcribe", help="transcribe and normalise a source")
    transcribe.add_argument("--item-id", required=True)
    transcribe.add_argument("--media", required=True)
    transcribe.add_argument(
        "--live",
        action="store_true",
        help="permit a real, paid provider call (also needs SPEAKING_EVAL_ALLOW_LIVE_PROVIDERS=true)",
    )
    transcribe.set_defaults(func=cmd_transcribe)

    review = sub.add_parser("review", help="generate the speaker-role review page")
    review.add_argument("--item-id", required=True)
    review.add_argument("--media", required=True)
    review.set_defaults(func=cmd_review)

    clips = sub.add_parser("clips", help="cut candidate clips and measure preparation")
    clips.add_argument("--item-id", required=True)
    clips.add_argument("--media", required=True)
    clips.add_argument("--annotation")
    clips.add_argument("--ground-truth")
    clips.add_argument(
        "--gating",
        action="store_true",
        help="apply the stricter checks required of an item that can block a release",
    )
    clips.set_defaults(func=cmd_clips)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
