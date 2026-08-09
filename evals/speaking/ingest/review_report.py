"""Static HTML speaker-role review page (SPEAK-EVAL-005, section 8.2).

The plan is explicit that a generated static page is sufficient for the first
implementation and that a browser automation agent is not needed. What is NOT
optional is that a human looks: role assignment and rights are judgements, and
this page exists to make the judgement cheap rather than to make it unnecessary.

The page presents the evidence a reviewer needs and stops short of the
conclusion. There is no pre-selected role, no "suggested" mapping and no
speaker ordering that hints at an answer -- a suggestion is the thing that gets
accepted without looking, and the entire value of this step is that somebody
looked.

Output is a single self-contained file with the audio referenced relatively, so
it opens from disk with no server.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from evals.speaking.ingest.normalize import NormalizedTranscript, speaker_summary


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def render(
    transcript: NormalizedTranscript,
    audio_path: Path,
    *,
    manifest_entry: dict | None = None,
) -> str:
    """Render the review page for one item."""
    summary = speaker_summary(transcript)
    audio_rel = _escape(audio_path.name)

    permission_block = "<p class='warn'>No manifest entry supplied — rights state unknown.</p>"
    if manifest_entry:
        permission = manifest_entry.get("permission", {})
        source = manifest_entry.get("source", {})
        permission_block = f"""
        <dl>
          <dt>Source kind</dt><dd>{_escape(source.get('kind', '?'))}</dd>
          <dt>Origin</dt><dd>{_escape(source.get('origin_url', '—'))}</dd>
          <dt>Permission</dt><dd><strong>{_escape(permission.get('status', 'unknown'))}</strong></dd>
          <dt>Basis</dt><dd>{_escape(permission.get('basis', '—'))}</dd>
          <dt>Governance ref</dt><dd>{_escape(permission.get('governance_ref', '—'))}</dd>
        </dl>"""

    flags = []
    if len(transcript.provider_speakers) != 2:
        flags.append(
            f"This recording has {len(transcript.provider_speakers)} speakers, not the "
            f"expected 2. Explain in the reviewer note before assigning roles."
        )
    overlaps = [u for u in transcript.utterances if u.overlap]
    if overlaps:
        flags.append(
            f"{len(overlaps)} utterance(s) overlap the previous speaker. Decide whether "
            f"the item is still usable."
        )
    low_confidence = [
        u for u in transcript.utterances
        if u.confidence is not None and u.confidence < 0.5
    ]
    if low_confidence:
        flags.append(
            f"{len(low_confidence)} utterance(s) are below 0.5 confidence. Check them "
            f"against the audio before trusting the text."
        )
    if transcript.quarantine:
        flags.append(
            f"{len(transcript.quarantine)} normalisation problem(s) were recorded. This "
            f"item is quarantined and cannot be used until they are resolved."
        )

    flags_html = ""
    if flags:
        items = "".join(f"<li>{_escape(f)}</li>" for f in flags)
        flags_html = f"<section class='flags'><h2>Review flags</h2><ul>{items}</ul></section>"

    speaker_cards = []
    for entry in summary:
        excerpts = "".join(
            f"""<li>
                  <button type="button" data-start="{e['start_s']}">
                    {e['start_s']:.2f}s
                  </button>
                  <span>{_escape(e['text'])}</span>
                </li>"""
            for e in entry["excerpts"]
        )
        speaker = entry["provider_speaker"]
        speaker_cards.append(f"""
        <article class="speaker">
          <h3>Provider speaker {_escape(speaker)}</h3>
          <p class="meta">
            {entry['utterance_count']} utterances ·
            {entry['total_duration_s']:.1f}s ·
            {entry['share_of_speech'] * 100:.0f}% of speech ·
            first heard at {entry['first_turn_s']:.2f}s
          </p>
          <ul class="excerpts">{excerpts}</ul>
          <label>
            Role
            <select data-speaker="{_escape(speaker)}">
              <option value="">— choose —</option>
              <option value="candidate">candidate</option>
              <option value="examiner">examiner</option>
              <option value="other">other</option>
            </select>
          </label>
        </article>""")

    transcript_rows = "".join(
        f"""<tr class="{'overlap' if u.overlap else ''}">
              <td><button type="button" data-start="{u.start_s}">{u.start_s:.2f}</button></td>
              <td>{u.end_s:.2f}</td>
              <td>{_escape(u.provider_speaker)}</td>
              <td>{('%.2f' % u.confidence) if u.confidence is not None else '—'}</td>
              <td>{_escape(u.normalized_text)}</td>
            </tr>"""
        for u in transcript.utterances
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Role review — {_escape(transcript.item_id)}</title>
<style>
  /* GOA design tokens, mirrored from services/frontend/app/globals.css.

     The first version of this page used ad-hoc colours -- #666 body text, #ddd
     card borders, #eee row rules, an #eef button. Several of those are below
     3:1 against white, so the structure was effectively invisible: the speaker
     cards and the transcript rules read as blank space. That matters more here
     than on most pages, because this is the screen where somebody decides which
     voice is the candidate, and a reviewer who cannot see the card boundaries
     cannot see which excerpts belong to which speaker.

     Tokens are duplicated rather than imported because this file has to open
     straight from disk with no server and no stylesheet fetch. This comment is
     the link back to the source of truth. */
  :root {{
    color-scheme: light;

    --color-sage-50:  #fafcfb;
    --color-sage-100: #f3f6f5;
    --color-sage-200: #e6ebe8;
    --color-sage-300: #d0d8d4;
    --color-sage-400: #9daaa3;
    --color-sage-600: #57665e;
    --color-sage-700: #43514a;
    --color-sage-800: #303b36;
    --color-sage-900: #1f2824;
    --color-sage-950: #121714;
    --color-forest-300: #89d1bc;
    --color-forest-400: #4fba9a;
    --color-forest-800: #0d4d3a;
    --color-forest-950: #07221b;

    --canvas: var(--color-sage-50);
    --canvas-subtle: var(--color-sage-100);
    --surface: #ffffff;
    --border: var(--color-sage-200);
    --border-strong: var(--color-sage-300);

    /* fg 15.9:1 - fg-muted 8.3:1 - fg-subtle 6.0:1 on surface */
    --fg: var(--color-sage-900);
    --fg-muted: var(--color-sage-700);
    --fg-subtle: var(--color-sage-600);

    --brand: var(--color-forest-800);
    --brand-fg: var(--color-forest-800);
    --brand-subtle: #effbf7;
    --brand-border: #bae8da;

    --warning: #a66a08; --warning-subtle: #fdf6e7;
    --warning-border: #f2dda9; --warning-fg: #855307;
    --danger: #b3341f; --danger-subtle: #fdf2f0;
    --danger-border: #f7d5ce; --danger-fg: #96291a;

    --focus-ring: #1e8063;

    /* Elevation, forest-tinted rather than pure black -- untinted black over a
       warm canvas is what makes a UI look cheap. e1 is what separates a card
       from the canvas when the two fills are close, which they deliberately
       are in this system. */
    --shadow-e1: 0 1px 2px 0 rgb(7 34 27 / 0.04), 0 1px 3px 0 rgb(7 34 27 / 0.06);
    --shadow-e2: 0 2px 4px -1px rgb(7 34 27 / 0.05), 0 8px 16px -4px rgb(7 34 27 / 0.08);
  }}

  @media (prefers-color-scheme: dark) {{
    :root {{
      color-scheme: dark;

      --canvas: var(--color-sage-950);
      --canvas-subtle: var(--color-sage-900);
      --surface: var(--color-sage-900);
      --border: var(--color-sage-800);
      --border-strong: var(--color-sage-700);

      --fg: var(--color-sage-50);
      --fg-muted: var(--color-sage-300);
      --fg-subtle: var(--color-sage-400);

      --brand: var(--color-forest-400);
      --brand-fg: var(--color-forest-300);
      --brand-subtle: var(--color-forest-950);
      --brand-border: #14674e;

      --warning: #d99a2b; --warning-subtle: #2a1d08;
      --warning-border: #57400f; --warning-fg: #f0c274;
      --danger: #d9563c; --danger-subtle: #2a1210;
      --danger-border: #5a2820; --danger-fg: #f0917d;

      --focus-ring: var(--color-forest-400);

      /* A shadow is invisible on a dark canvas. Separation comes from the
         border there instead, so elevation is flattened rather than tinted
         darker -- a darker shadow on a dark surface reads as nothing at all. */
      --shadow-e1: none;
      --shadow-e2: none;
    }}
  }}

  body {{
    font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    margin: 0 auto; max-width: 64rem; padding: 2rem 1.5rem 4rem;
    background: var(--canvas); color: var(--fg);
  }}
  h1 {{ margin: 0 0 0.25rem; font-size: 1.6rem; letter-spacing: -0.01em; }}
  h2 {{ font-size: 1.15rem; margin: 0 0 0.75rem; }}
  .sub {{ color: var(--fg-muted); margin-top: 0; }}
  section {{ margin: 2rem 0; }}

  dl {{ display: grid; grid-template-columns: 10rem 1fr; gap: 0.4rem 1rem; margin: 0; }}
  dt {{ font-weight: 600; color: var(--fg-muted); }}
  dd {{ margin: 0; }}

  .flags {{
    background: var(--warning-subtle); color: var(--warning-fg);
    border: 1px solid var(--warning-border); border-left: 3px solid var(--warning);
    padding: 1rem 1.25rem; border-radius: 0 0.5rem 0.5rem 0;
  }}
  .flags h2 {{ color: inherit; }}
  .warn {{
    background: var(--danger-subtle); color: var(--danger-fg);
    border: 1px solid var(--danger-border); border-left: 3px solid var(--danger);
    padding: 0.75rem 1rem; border-radius: 0 0.5rem 0.5rem 0;
  }}

  .speakers {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(21rem, 1fr)); gap: 1rem; }}
  .speaker {{
    background: var(--surface); border: 1px solid var(--border-strong);
    border-radius: 1rem; padding: 1.25rem; box-shadow: var(--shadow-e1);
  }}
  .speaker h3 {{ margin: 0 0 0.35rem; font-size: 1rem; }}
  .meta {{ color: var(--fg-subtle); font-size: 0.875rem; margin: 0 0 0.75rem; }}

  .excerpts {{ list-style: none; padding: 0; margin: 0 0 1rem; }}
  .excerpts li {{ display: flex; gap: 0.5rem; margin-bottom: 0.45rem; align-items: baseline; }}

  button {{
    cursor: pointer; font: inherit; font-size: 0.8125rem;
    font-variant-numeric: tabular-nums;
    background: var(--brand-subtle); color: var(--brand-fg);
    border: 1px solid var(--brand-border); border-radius: 0.375rem;
    padding: 0.1rem 0.45rem; white-space: nowrap;
  }}
  button:hover {{ background: var(--surface); border-color: var(--brand); }}
  :focus-visible {{ outline: 2px solid var(--focus-ring); outline-offset: 2px; }}

  select {{
    font: inherit; padding: 0.4rem 0.5rem; border-radius: 0.375rem;
    border: 1px solid var(--border-strong);
    background: var(--surface); color: var(--fg);
  }}
  label {{ display: block; font-weight: 600; font-size: 0.875rem; color: var(--fg-muted); }}
  label select {{ display: block; margin-top: 0.3rem; width: 100%; font-weight: 400; color: var(--fg); }}

  table {{
    border-collapse: collapse; width: 100%; font-size: 0.9rem;
    background: var(--surface); border: 1px solid var(--border-strong);
    border-radius: 0.75rem; overflow: hidden; box-shadow: var(--shadow-e1);
  }}
  th, td {{
    border-bottom: 1px solid var(--border);
    padding: 0.45rem 0.6rem; text-align: left; vertical-align: top;
  }}
  th {{
    background: var(--canvas-subtle); color: var(--fg-muted);
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
    position: sticky; top: 0;
  }}
  td:nth-child(-n+4) {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  /* Overlap is a review decision, so it is tinted rather than merely noted --
     but tinted with the warning token, which carries a readable foreground.
     The previous #fff6e5 fill kept the default near-black text and was easy to
     miss entirely. */
  tr.overlap {{ background: var(--warning-subtle); color: var(--warning-fg); }}

  #out {{
    width: 100%; min-height: 9rem; font-family: ui-monospace, monospace;
    font-size: 0.8125rem; padding: 0.75rem; border-radius: 0.5rem;
    border: 1px solid var(--border-strong);
    background: var(--canvas-subtle); color: var(--fg);
  }}
  audio {{ width: 100%; }}
  code {{
    font-family: ui-monospace, monospace; font-size: 0.875em;
    background: var(--canvas-subtle); padding: 0.1em 0.35em; border-radius: 0.25rem;
  }}
</style>
</head>
<body>
<h1>Speaker role review</h1>
<p class="sub">Item <code>{_escape(transcript.item_id)}</code> ·
   {_escape(transcript.provider)} {_escape(transcript.api_version)} ·
   job <code>{_escape(transcript.job_id)}</code></p>

<section>
  <h2>Rights and source</h2>
  {permission_block}
</section>

{flags_html}

<section>
  <h2>Audio</h2>
  <audio id="player" controls preload="metadata" src="{audio_rel}"></audio>
</section>

<section>
  <h2>Assign a role to each speaker</h2>
  <p>
    The provider numbers speakers by first appearance and does not know who is who.
    <strong>Speaker 0 is not automatically the candidate</strong> — in a typical IELTS
    recording the examiner speaks first, so speaker 0 is usually the examiner.
    Listen before choosing.
  </p>
  <div class="speakers">{''.join(speaker_cards)}</div>
</section>

<section>
  <h2>Full diarized transcript</h2>
  <table>
    <thead><tr><th>Start</th><th>End</th><th>Speaker</th><th>Conf.</th><th>Text</th></tr></thead>
    <tbody>{transcript_rows}</tbody>
  </table>
</section>

<section>
  <h2>Annotation</h2>
  <p>Assign every speaker above, then copy this into the item's annotation file.</p>
  <textarea id="out" readonly></textarea>
</section>

<script>
  const player = document.getElementById('player');
  document.querySelectorAll('button[data-start]').forEach(function (b) {{
    b.addEventListener('click', function () {{
      player.currentTime = parseFloat(b.dataset.start);
      player.play();
    }});
  }});

  const base = {json.dumps({
      "schema_version": "role-annotation/v1",
      "item_id": transcript.item_id,
      "normalized_sha256": transcript.content_sha256(),
  })};

  function refresh() {{
    const roles = {{}};
    document.querySelectorAll('select[data-speaker]').forEach(function (s) {{
      if (s.value) roles[s.dataset.speaker] = s.value;
    }});
    document.getElementById('out').value = JSON.stringify(
      Object.assign({{}}, base, {{
        speaker_roles: roles,
        reviewers: [],
        reviewed_at: null,
        boundary_edits: [],
        notes: "",
        contaminated: false,
        exclusion_reason: null
      }}), null, 2);
  }}

  document.querySelectorAll('select[data-speaker]').forEach(function (s) {{
    s.addEventListener('change', refresh);
  }});
  refresh();
</script>
</body>
</html>
"""


def write_report(
    transcript: NormalizedTranscript,
    audio_path: Path,
    out_path: Path,
    *,
    manifest_entry: dict | None = None,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render(transcript, audio_path, manifest_entry=manifest_entry), encoding="utf-8"
    )
    return out_path
