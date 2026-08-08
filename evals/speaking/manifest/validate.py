"""Validators for the speaking evaluation dataset manifest (SPEAK-EVAL-004).

A manifest that merely *describes* the dataset is a document. These validators
are what make it binding: they are the difference between "we intend not to gate
on unvalidated items" and "an unvalidated item cannot reach a gating split".

Four rules, one per acceptance criterion:

1. An item in a gating split must be permitted, human-validated, and hashed.
2. A candidate or a source series may not appear in more than one split.
3. An item claiming permission must name who granted it and record an integrity
   hash.
4. Restricted audio may not be stored in the repository, and no audio file may
   sit in the dataset tree undeclared.

Run standalone:

    python evals/speaking/manifest/validate.py

Exit code 0 means the manifest is safe to gate on.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "manifest.json"
SCHEMA = HERE / "schema" / "dataset-manifest-v1.schema.json"

# Audio extensions the tree is swept for. A file with one of these under the
# manifest directory must be declared, or rule 4 fails.
AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".opus", ".aac"}

# Label provenance that can never support a published accuracy number. A band a
# model assigned to a transcript a model wrote measures self-agreement.
UNGATEABLE_LABEL_SOURCES = {"model_generated", "none"}

# Permission states that allow use. `unknown` is absent on purpose: an item
# nobody has reviewed is not a permitted item, and defaulting the other way is
# how an unreviewed recording ends up in a published result.
PERMITTED_STATUSES = {"granted", "not_required"}


@dataclass(frozen=True)
class Problem:
    """One rule violation, addressed to whoever has to fix it."""

    rule: str
    item_id: str | None
    message: str

    def __str__(self) -> str:
        where = f" [{self.item_id}]" if self.item_id else ""
        return f"{self.rule}{where}: {self.message}"


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def gating_splits(manifest: dict) -> set[str]:
    return {
        name
        for name, split in manifest.get("splits", {}).items()
        if split.get("gating") is True
    }


def gating_items(manifest: dict) -> list[dict]:
    """The items that may contribute to a number capable of blocking a release.

    Callers should use this rather than filtering items themselves. The whole
    point of the manifest is that the eligibility question has exactly one
    answer, computed in one place.
    """
    gating = gating_splits(manifest)
    return [item for item in manifest.get("items", []) if item.get("split") in gating]


def check_schema(manifest: dict) -> list[Problem]:
    """Structural validation, when jsonschema is available.

    Skipped rather than failed when the library is absent: the four rules below
    are the substance, and they do not depend on it. A missing dev dependency
    should not be able to report a governance failure that is not there.
    """
    try:
        import jsonschema
    except ImportError:
        return []

    with SCHEMA.open(encoding="utf-8") as handle:
        schema = json.load(handle)

    validator = jsonschema.Draft202012Validator(schema)
    problems = []
    for error in validator.iter_errors(manifest):
        location = ".".join(str(p) for p in error.absolute_path) or "<root>"
        problems.append(Problem("schema", None, f"{location}: {error.message}"))
    return problems


def check_gating_eligibility(manifest: dict) -> list[Problem]:
    """Rule 1 -- invalid, unlicensed or unvalidated items cannot gate."""
    problems = []
    declared = set(manifest.get("splits", {}))

    for item in manifest.get("items", []):
        item_id = item.get("item_id")
        split = item.get("split")

        if split not in declared:
            problems.append(
                Problem("gating", item_id, f"split {split!r} is not declared in `splits`")
            )
            continue

        if split not in gating_splits(manifest):
            continue

        permission = item.get("permission", {})
        if permission.get("status") not in PERMITTED_STATUSES:
            problems.append(
                Problem(
                    "gating",
                    item_id,
                    f"is in gating split {split!r} with permission status "
                    f"{permission.get('status')!r}; only {sorted(PERMITTED_STATUSES)} may gate",
                )
            )

        labels = item.get("labels", {})
        if labels.get("validated") is not True:
            problems.append(
                Problem(
                    "gating",
                    item_id,
                    f"is in gating split {split!r} but its band was never validated by a human",
                )
            )
        if labels.get("source") in UNGATEABLE_LABEL_SOURCES:
            problems.append(
                Problem(
                    "gating",
                    item_id,
                    f"is in gating split {split!r} with label source "
                    f"{labels.get('source')!r}; such a band measures agreement with a "
                    f"model, not accuracy",
                )
            )
        if labels.get("source") == "commissioned_double_rated":
            raters = labels.get("raters") or []
            if len(raters) < 2:
                problems.append(
                    Problem(
                        "gating",
                        item_id,
                        f"claims double rating but names {len(raters)} rater(s)",
                    )
                )
        if labels.get("overall_band") is None:
            problems.append(
                Problem("gating", item_id, f"is in gating split {split!r} with no band")
            )

        media = item.get("media", {})
        if media.get("storage") == "none":
            problems.append(
                Problem(
                    "gating",
                    item_id,
                    f"is in gating split {split!r} with no audio; the speaking "
                    f"pipeline scores audio, and a transcript-only item cannot exercise it",
                )
            )
        elif not media.get("sha256"):
            problems.append(
                Problem(
                    "gating",
                    item_id,
                    f"is in gating split {split!r} with no integrity hash",
                )
            )

    return problems


def check_split_leakage(manifest: dict) -> list[Problem]:
    """Rule 2 -- a candidate or a series may not cross splits.

    Both matter. The same speaker on both sides of a comparison inflates it
    obviously; the same *series* does so quietly, because one recording shares
    an examiner, a microphone and an editing pass, and a model that has seen one
    answer from it has seen the conditions of the rest.
    """
    problems = []

    for field in ("candidate_id", "series_id"):
        splits_by_key: dict[str, set[str]] = collections.defaultdict(set)
        items_by_key: dict[str, list[str]] = collections.defaultdict(list)

        for item in manifest.get("items", []):
            key = item.get(field)
            if key is None:
                continue
            splits_by_key[key].add(item.get("split"))
            items_by_key[key].append(item.get("item_id"))

        for key, splits in sorted(splits_by_key.items()):
            if len(splits) > 1:
                problems.append(
                    Problem(
                        "leakage",
                        None,
                        f"{field} {key!r} appears in {len(splits)} splits "
                        f"({', '.join(sorted(str(s) for s in splits))}) "
                        f"across items {', '.join(sorted(items_by_key[key]))}",
                    )
                )

    return problems


def check_permission_records(manifest: dict) -> list[Problem]:
    """Rule 3 -- an approved source names its approval and carries a hash."""
    problems = []

    for item in manifest.get("items", []):
        item_id = item.get("item_id")
        permission = item.get("permission", {})
        status = permission.get("status")

        if status not in PERMITTED_STATUSES:
            continue

        if not permission.get("basis"):
            problems.append(
                Problem(
                    "governance",
                    item_id,
                    f"permission is {status!r} with no stated basis",
                )
            )
        if not permission.get("governance_ref"):
            problems.append(
                Problem(
                    "governance",
                    item_id,
                    f"permission is {status!r} with no governance reference",
                )
            )
        if status == "granted" and not permission.get("reviewed_by"):
            problems.append(
                Problem(
                    "governance",
                    item_id,
                    "permission is granted but nobody is recorded as having reviewed it",
                )
            )

        media = item.get("media", {})
        if media.get("storage") != "none" and not media.get("sha256"):
            problems.append(
                Problem(
                    "governance",
                    item_id,
                    "has media but no integrity hash, so a silent replacement "
                    "would be undetectable",
                )
            )

    return problems


def check_restricted_media(manifest: dict, root: Path = HERE) -> list[Problem]:
    """Rule 4 -- restricted audio stays out of the repository.

    Two directions, because either alone leaves the hole open. The manifest is
    checked for an item that claims both `restricted` and `storage: repo`; then
    the tree is swept for audio that no item declares, which is what an
    accidental `git add` of a downloaded recording actually looks like.
    """
    problems = []
    declared_paths: dict[str, str] = {}

    for item in manifest.get("items", []):
        item_id = item.get("item_id")
        media = item.get("media", {})
        storage = media.get("storage")

        if media.get("restricted") is True and storage == "repo":
            problems.append(
                Problem(
                    "restricted-media",
                    item_id,
                    "is marked restricted and stored in the repository",
                )
            )

        if storage == "repo":
            path = media.get("path")
            if not path:
                problems.append(
                    Problem("restricted-media", item_id, "storage is repo but no path is given")
                )
                continue

            declared_paths[path] = item_id
            resolved = (root.parents[2] / path) if not Path(path).is_absolute() else Path(path)
            if not resolved.exists():
                problems.append(
                    Problem("restricted-media", item_id, f"declared media {path} does not exist")
                )
            elif media.get("sha256"):
                actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
                if actual != media["sha256"]:
                    problems.append(
                        Problem(
                            "restricted-media",
                            item_id,
                            f"media hash mismatch: manifest says {media['sha256'][:12]}..., "
                            f"file is {actual[:12]}...",
                        )
                    )

    declared_names = {Path(p).name for p in declared_paths}
    for found in sorted(root.rglob("*")):
        if not found.is_file() or found.suffix.lower() not in AUDIO_SUFFIXES:
            continue
        if found.name not in declared_names:
            problems.append(
                Problem(
                    "restricted-media",
                    None,
                    f"undeclared audio file in the dataset tree: "
                    f"{found.relative_to(root)}. Every audio file must be declared "
                    f"in the manifest, or it has no recorded licence.",
                )
            )

    return problems


def validate(manifest: dict, root: Path = HERE) -> list[Problem]:
    """Run every rule and return the problems, most structural first."""
    return (
        check_schema(manifest)
        + check_gating_eligibility(manifest)
        + check_split_leakage(manifest)
        + check_permission_records(manifest)
        + check_restricted_media(manifest, root)
    )


def summarise(manifest: dict) -> str:
    """A one-glance count, so a quarantine that quietly emptied is visible."""
    by_split: dict[str, int] = collections.Counter(
        item.get("split") for item in manifest.get("items", [])
    )
    gating = gating_splits(manifest)
    lines = []
    for split in sorted(by_split):
        marker = "GATING" if split in gating else "non-gating"
        lines.append(f"  {split:<12} {by_split[split]:>3} items  ({marker})")
    lines.append(f"  {'gating total':<12} {len(gating_items(manifest)):>3} items")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"error: no manifest at {args.manifest}", file=sys.stderr)
        return 2

    manifest = load_manifest(args.manifest)
    print(f"speaking dataset manifest: {args.manifest}")
    print(summarise(manifest))
    print()

    problems = validate(manifest, root=args.manifest.parent)
    if problems:
        print(f"FAILED: {len(problems)} governance problem(s)")
        for problem in problems:
            print(f"  {problem}")
        return 1

    print("PASSED: every rule holds; the gating splits are safe to publish from")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
