"""
Grades an agent's IELTS evaluation against the official band descriptors and returns
ACCURATE / OVERSCORED / UNDERSCORED with a reason.

The single most important rule in this file: **the model supplies the reason, the code
supplies the verdict.** Asking a model for a label it can also justify invites drift —
it will talk itself into ACCURATE. The band arithmetic is deterministic and lives here.
"""

import hashlib
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional


RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"
CACHE_FILE = Path(__file__).resolve().parent / ".judge_cache.json"

RUBRIC_FILES = {
    "writing": "writing_task2.md",
    "speaking": "speaking.md",
}

CRITERIA: Dict[str, Tuple[str, ...]] = {
    "writing": ("task_response", "coherence", "lexical", "grammar"),
    "speaking": ("fluency", "lexical", "grammar", "pronunciation"),
}

ACCURATE_TOLERANCE = 0.5  # Ticket definition: within half a band of expert is correct.

def get_model() -> str:
    return os.environ.get("EVAL_JUDGE_MODEL", "claude-opus-4-8")


@dataclass
class JudgeVerdict:
    item_id: str
    verdict: str  # ACCURATE | OVERSCORED | UNDERSCORED | ERROR
    agent_band: float
    expert_band: float
    delta: float
    reason: str
    judged_band: Optional[float] = None
    agent_criteria: dict = field(default_factory=dict)      # agent's bands -> feeds MAE
    expert_criteria: dict = field(default_factory=dict)     # ground truth -> feeds MAE
    judge_criteria: dict = field(default_factory=dict)      # judge's assessment -> disagreement signal
    per_criterion_verdicts: dict = field(default_factory=dict) # per-criterion ACCURATE/OVERSCORED/UNDERSCORED
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


def _load_disk_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_disk_cache(cache_data: dict) -> None:
    try:
        CACHE_FILE.write_text(json.dumps(cache_data, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_cache_key(domain: str, text: str, agent_band: float, model: Optional[str] = None) -> str:
    m = model or get_model()
    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{domain}:{m}:{text_sha}:{agent_band}"


def load_rubric(domain: str) -> str:
    """Read official descriptors from disk. Fail fast if missing."""
    clean_domain = "writing" if domain.startswith("writing") else domain
    filename = RUBRIC_FILES.get(clean_domain, f"{clean_domain}.md")
    path = RUBRIC_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Missing rubric {path}. The judge must grade against official "
            f"descriptors; refusing to run on model memory."
        )
    return path.read_text(encoding="utf-8")


def compute_verdict(agent_band: float, expert_band: float) -> str:
    """The verdict, in code. Never taken from the model."""
    delta = agent_band - expert_band
    if abs(delta) <= ACCURATE_TOLERANCE:
        return "ACCURATE"
    return "OVERSCORED" if delta > 0 else "UNDERSCORED"


def build_judge_prompt(domain: str, text: str, agent_evaluation: dict, rubric: str) -> str:
    """The judge sees: descriptors, candidate work, and what the agent said."""
    domain_key = "writing" if domain.startswith("writing") else domain
    domain_criteria = CRITERIA.get(domain_key, ("task_response", "coherence", "lexical", "grammar"))
    
    template_props = ", ".join(f'"{c}": <number>' for c in domain_criteria)
    criteria_lines = "\n".join(
        f"  - {name}: band {value}"
        for name, value in (agent_evaluation.get("criteria") or {}).items()
    )
    justification = agent_evaluation.get("justification") or "(none provided)"
    label = "ESSAY" if domain_key == "writing" else "TRANSCRIPT"

    return f"""You are an IELTS examiner reviewing another examiner's marking.

OFFICIAL BAND DESCRIPTORS — grade against these and nothing else:
{rubric}

CANDIDATE {label}:
{text}

THE OTHER EXAMINER'S MARKING:
  Overall band: {agent_evaluation.get("overall_band")}
{criteria_lines}
  Their justification: {justification}

Your task: decide, for each criterion and overall, what band the descriptors actually
support for this work. Judge against the descriptor language, not against your own
preferred style of answer.

Quote the specific descriptor wording you relied on. If you cannot ground a judgement
in the descriptors above, say so rather than inventing one.

Return ONLY this JSON object, with no prose before or after:
{{
  "judged_band": <number>,
  "per_criterion": {{{template_props}}},
  "reason": "<2-3 sentences quoting descriptor language>"
}}"""


def _extract_text(response) -> Tuple[str, int, int]:
    """Extract text and token usage from response."""
    text_content = ""
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            text_content = text
            break
    
    usage = getattr(response, "usage", None)
    in_toks = getattr(usage, "input_tokens", 0) if usage else 0
    out_toks = getattr(usage, "output_tokens", 0) if usage else 0
    return text_content, in_toks, out_toks


def _parse_json_object(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in judge response: {raw[:200]}")
    return json.loads(match.group(0))


def _client():
    from anthropic import Anthropic

    kwargs = {
        "api_key": os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_API_KEY", ""),
        "default_headers": {
            "User-Agent": os.environ.get("ANTHROPIC_USER_AGENT")
            or "Kilo-Code/7.4.11 ai-sdk/provider-utils/4.0.27 runtime/bun/1.3.14"
        },
        "timeout": 60.0,
    }
    if os.environ.get("ANTHROPIC_BASE_URL"):
        kwargs["base_url"] = os.environ["ANTHROPIC_BASE_URL"]
    return Anthropic(**kwargs)


def judge_evaluation(domain: str, item: dict, agent_result: dict,
                     client=None, rubric: Optional[str] = None,
                     attempts: int = 2, use_cache: bool = True) -> JudgeVerdict:
    """Judge one item. Never raises: a failure is recorded, not thrown."""
    item_id = item.get("id", "<unknown>")
    expert_band = float(item.get("expected_band", 0.0))
    expert_criteria = item.get("expected_criteria", {})
    agent_criteria = agent_result.get("criteria", {})
    text = item.get("essay") or item.get("transcript") or ""

    # The agent call failed upstream. Spend no tokens judging a band that does not
    # exist, and — critically — do not let it reach compute_verdict, which would
    # coerce the absence into 0.0 and report a confident UNDERSCORED.
    if agent_result.get("agent_error"):
        return JudgeVerdict(
            item_id=item_id,
            verdict="ERROR",
            agent_band=float("nan"),
            expert_band=expert_band,
            delta=float("nan"),
            reason="",
            judged_band=None,
            agent_criteria=agent_criteria,
            expert_criteria=expert_criteria,
            error=f"Agent call failed: {agent_result['agent_error']}",
        )

    agent_band = float(agent_result.get("overall_band") or 0.0)

    # Compute per-criterion verdicts
    per_criterion_verdicts = {}
    for c_key, c_agent in agent_criteria.items():
        if c_key in expert_criteria:
            per_criterion_verdicts[c_key] = compute_verdict(float(c_agent), float(expert_criteria[c_key]))

    cache_key = get_cache_key(domain, text, agent_band, get_model())
    if use_cache:
        disk_cache = _load_disk_cache()
        if cache_key in disk_cache:
            cached_data = disk_cache[cache_key]
            return JudgeVerdict(
                item_id=item_id,
                verdict=compute_verdict(agent_band, expert_band),
                agent_band=agent_band,
                expert_band=expert_band,
                delta=round(agent_band - expert_band, 2),
                reason=cached_data.get("reason", ""),
                judged_band=cached_data.get("judged_band"),
                agent_criteria=agent_criteria,
                expert_criteria=expert_criteria,
                judge_criteria=cached_data.get("per_criterion", {}),
                per_criterion_verdicts=per_criterion_verdicts,
                input_tokens=0,
                output_tokens=0,
                cached=True,
            )

    try:
        rubric_text = rubric or load_rubric(domain)
    except Exception as e:
        return JudgeVerdict(
            item_id=item_id,
            verdict="ERROR",
            agent_band=agent_band,
            expert_band=expert_band,
            delta=round(agent_band - expert_band, 2),
            reason="",
            judged_band=None,
            agent_criteria=agent_criteria,
            expert_criteria=expert_criteria,
            per_criterion_verdicts=per_criterion_verdicts,
            error=f"Rubric load failed: {e}",
        )

    base_prompt = build_judge_prompt(domain, text, agent_result, rubric_text)

    if client is None:
        try:
            client = _client()
        except Exception as e:
            return JudgeVerdict(
                item_id=item_id,
                verdict="ERROR",
                agent_band=agent_band,
                expert_band=expert_band,
                delta=round(agent_band - expert_band, 2),
                reason="",
                judged_band=None,
                agent_criteria=agent_criteria,
                expert_criteria=expert_criteria,
                per_criterion_verdicts=per_criterion_verdicts,
                error=f"Client initialization failed: {e}",
            )

    last_error = None
    current_prompt = base_prompt

    for attempt in range(attempts):
        try:
            response = client.messages.create(
                model=get_model(),
                max_tokens=1500,
                messages=[{"role": "user", "content": current_prompt}],
            )
            raw_text, in_toks, out_toks = _extract_text(response)
            parsed = _parse_json_object(raw_text)
            
            judged_band = parsed.get("judged_band")
            if judged_band is not None:
                judged_band = float(judged_band)

            if use_cache:
                disk_cache = _load_disk_cache()
                disk_cache[cache_key] = parsed
                _save_disk_cache(disk_cache)

            return JudgeVerdict(
                item_id=item_id,
                verdict=compute_verdict(agent_band, expert_band),
                agent_band=agent_band,
                expert_band=expert_band,
                delta=round(agent_band - expert_band, 2),
                reason=parsed.get("reason", ""),
                judged_band=judged_band,
                agent_criteria=agent_criteria,
                expert_criteria=expert_criteria,
                judge_criteria=parsed.get("per_criterion", {}),
                per_criterion_verdicts=per_criterion_verdicts,
                input_tokens=in_toks,
                output_tokens=out_toks,
                cached=False,
            )
        except Exception as e:
            last_error = e
            current_prompt = (
                f"{base_prompt}\n\n[RETRY] Your previous response could not be parsed: {e}\n"
                "Output ONLY the JSON object described above. No explanation, no "
                "apology, no questions."
            )

    return JudgeVerdict(
        item_id=item_id,
        verdict="ERROR",
        agent_band=agent_band,
        expert_band=expert_band,
        delta=round(agent_band - expert_band, 2),
        reason="",
        judged_band=None,
        agent_criteria=agent_criteria,
        expert_criteria=expert_criteria,
        per_criterion_verdicts=per_criterion_verdicts,
        error=str(last_error),
    )


def judge_all(domain: str, items: List[dict], agent_results: List[dict],
              client=None, max_workers: int = 4) -> List[JudgeVerdict]:
    """Judge all items. Fail fast on missing rubric, strictly assert equal list lengths."""
    assert len(items) == len(agent_results), (
        f"{len(items)} items but {len(agent_results)} agent results — a dropped agent "
        f"call must be an errored verdict, not a shorter list"
    )

    rubric = load_rubric(domain)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(judge_evaluation, domain, item, agent_res, client, rubric)
            for item, agent_res in zip(items, agent_results)
        ]
        return [f.result() for f in futures]
