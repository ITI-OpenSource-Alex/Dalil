"use client";

/**
 * Renders the explanation a speaking session was scored with (SPEAK-EVAL-008).
 *
 * Shared by practice, history and exam so all three show the same thing. Three
 * surfaces rendering the same score three ways is how a student comes to
 * believe the number changed.
 *
 * This component displays what the server decided may be displayed. It does not
 * look up rubric text, does not resolve quotes, and does not reconstruct a
 * withheld claim from the raw evaluation — the validator removed those on
 * purpose, and rebuilding them here would put them back one layer further from
 * the check.
 */

import {
  type Claim,
  type ExplanationMeta,
  type Renderable,
  type RenderableCriterion,
  claimsOfKind,
  criterionLabel,
  isScored,
  polarityCopy,
  scoreSemanticsCopy,
  unavailableCopy,
  withheldNotice,
} from "@/lib/speaking-explanation";

interface Props {
  renderable: Renderable;
  meta?: ExplanationMeta;
  /** The transcript the offsets refer to, when the surface has it. */
  transcript?: string;
}

export function SpeakingExplanation({ renderable, meta, transcript }: Props) {
  const criteria = renderable.Criteria ?? [];

  return (
    <section aria-labelledby="explanation-heading" className="space-y-6">
      <div>
        <h2 id="explanation-heading" className="text-lg font-semibold text-fg">
          How this was assessed
        </h2>
        {/* The qualifier travels with the band, always. A band shown without it
            implies a certified assessment, which this system must never claim. */}
        <p className="mt-1 text-sm text-fg-subtle">
          {scoreSemanticsCopy(renderable.ScoreSemantics)}
        </p>
      </div>

      {renderable.BandWithheldReason && (
        <div
          role="status"
          className="rounded-card border border-warning-border bg-warning-subtle p-4 text-sm text-warning-fg"
        >
          {renderable.BandWithheldReason}
        </div>
      )}

      <ul className="space-y-4">
        {criteria.map((criterion) => (
          <li key={criterion.CriterionID}>
            <CriterionCard criterion={criterion} transcript={transcript} />
          </li>
        ))}
      </ul>

      {meta && <Provenance meta={meta} renderable={renderable} />}
    </section>
  );
}

function CriterionCard({
  criterion,
  transcript,
}: {
  criterion: RenderableCriterion;
  transcript?: string;
}) {
  const headingId = `criterion-${criterion.CriterionID}`;
  const scored = isScored(criterion);
  const withheldCount = criterion.Withheld?.length ?? 0;
  const notice = withheldNotice(withheldCount);

  return (
    <article
      aria-labelledby={headingId}
      className="rounded-card border border-border bg-surface p-5"
    >
      <header className="flex items-baseline justify-between gap-4">
        <h3 id={headingId} className="font-semibold text-fg">
          {criterionLabel(criterion.CriterionID)}
        </h3>
        {scored ? (
          <span className="text-2xl font-bold tabular-nums text-fg">
            {criterion.Band.toFixed(1)}
          </span>
        ) : (
          /* No number at all, not a dash that could read as zero. Band 0.0 is a
             real IELTS value and must never stand in for "not measured". */
          <span className="rounded-chip border border-border-strong bg-canvas-subtle px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-fg-muted">
            Not assessed
          </span>
        )}
      </header>

      {!scored && (
        <p className="mt-2 text-sm text-fg-muted">
          {unavailableCopy(criterion.UnavailableReason)}
        </p>
      )}

      {scored && (
        <>
          <RubricClaims criterion={criterion} />
          <EvidenceClaims criterion={criterion} transcript={transcript} />
          <SummaryClaims criterion={criterion} />
          <ActionClaims criterion={criterion} />
        </>
      )}

      {criterion.Limitations && criterion.Limitations.length > 0 && (
        <div className="mt-4 border-t border-border pt-3">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
            What this does not cover
          </h4>
          <ul className="mt-1 space-y-1 text-sm text-fg-subtle">
            {criterion.Limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      )}

      {notice && (
        /* Suppression is stated, never silent. A student comparing two sessions
           should be able to tell a quiet one from a broken one. */
        <p role="status" className="mt-3 text-xs text-fg-subtle">
          {notice}
        </p>
      )}
    </article>
  );
}

function RubricClaims({ criterion }: { criterion: RenderableCriterion }) {
  const claims = claimsOfKind(criterion, "rubric");
  if (claims.length === 0) return null;

  return (
    <div className="mt-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
        Against the official descriptors
      </h4>
      <ul className="mt-2 space-y-2">
        {claims.map((claim) => (
          <li
            key={`${claim.DescriptorID}-${claim.Polarity}`}
            className="rounded-chip border border-border bg-canvas-subtle p-3"
          >
            <p className="text-xs font-semibold text-brand-fg">
              {polarityCopy(claim.Polarity)}
              {typeof claim.DescriptorBand === "number" && (
                <> · Band {claim.DescriptorBand.toFixed(0)}</>
              )}
            </p>
            <p className="mt-1 text-sm text-fg">{claim.Text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceClaims({
  criterion,
  transcript,
}: {
  criterion: RenderableCriterion;
  transcript?: string;
}) {
  const claims = claimsOfKind(criterion, "evidence");
  if (claims.length === 0) return null;

  return (
    <div className="mt-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
        From your answer
      </h4>
      <ul className="mt-2 space-y-2">
        {claims.map((claim, index) => (
          <li key={index} className="text-sm">
            <EvidenceBody claim={claim} transcript={transcript} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidenceBody({
  claim,
  transcript,
}: {
  claim: Claim;
  transcript?: string;
}) {
  if (claim.Quote) {
    return (
      <>
        <blockquote className="border-l-2 border-brand-border pl-3 italic text-fg">
          “{claim.Quote}”
        </blockquote>
        <p className="mt-1 text-fg-muted">{claim.Text}</p>
        {/* Offsets are shown only when the surface actually holds the
            transcript. Offering to jump into text the page does not have would
            be a control that cannot work. */}
        {transcript && typeof claim.CharStart === "number" && (
          <p className="mt-0.5 text-xs text-fg-subtle">
            In your transcript at character {claim.CharStart}
          </p>
        )}
      </>
    );
  }

  if (typeof claim.MeasurementValue === "number") {
    return (
      <>
        <p className="text-fg">
          <span className="font-semibold tabular-nums">
            {claim.MeasurementValue}
          </span>{" "}
          <span className="text-fg-muted">{claim.MeasurementUnit}</span>
        </p>
        <p className="mt-0.5 text-fg-muted">{claim.Text}</p>
      </>
    );
  }

  if (typeof claim.AudioStartS === "number") {
    return (
      <>
        <p className="text-fg">{claim.Text}</p>
        <p className="mt-0.5 text-xs text-fg-subtle tabular-nums">
          {claim.AudioStartS.toFixed(1)}s – {claim.AudioEndS?.toFixed(1)}s
        </p>
      </>
    );
  }

  return <p className="text-fg-muted">{claim.Text}</p>;
}

function SummaryClaims({ criterion }: { criterion: RenderableCriterion }) {
  const claims = claimsOfKind(criterion, "summary");
  if (claims.length === 0) return null;

  return (
    <div className="mt-4 space-y-2">
      {claims.map((claim, index) => (
        <p key={index} className="text-sm text-fg">
          {claim.Text}
        </p>
      ))}
    </div>
  );
}

function ActionClaims({ criterion }: { criterion: RenderableCriterion }) {
  const claims = claimsOfKind(criterion, "action");
  if (claims.length === 0) return null;

  return (
    <div className="mt-4">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
        What to practise
      </h4>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-fg">
        {claims.map((claim, index) => (
          <li key={index}>{claim.Text}</li>
        ))}
      </ul>
    </div>
  );
}

function Provenance({
  meta,
  renderable,
}: {
  meta: ExplanationMeta;
  renderable: Renderable;
}) {
  return (
    <details className="rounded-card border border-border bg-canvas-subtle p-4">
      <summary className="cursor-pointer text-sm font-medium text-fg-muted">
        How this assessment was produced
      </summary>
      <dl className="mt-3 grid grid-cols-[10rem_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-fg-muted">Rubric</dt>
        <dd className="text-fg">
          {meta.rubric_id} ({meta.rubric_version})
        </dd>
        <dt className="text-fg-muted">Assessed by</dt>
        <dd className="text-fg">{meta.scorer_version}</dd>
        {meta.llm_model && (
          <>
            <dt className="text-fg-muted">Model</dt>
            <dd className="text-fg">{meta.llm_model}</dd>
          </>
        )}
        <dt className="text-fg-muted">Observations</dt>
        <dd className="text-fg tabular-nums">
          {meta.claim_count} shown
          {meta.withheld_count > 0 && <>, {meta.withheld_count} unverified</>}
        </dd>
        {typeof renderable.UnroundedMean === "number" && (
          <>
            <dt className="text-fg-muted">Before rounding</dt>
            <dd className="text-fg tabular-nums">
              {renderable.UnroundedMean.toFixed(2)}
            </dd>
          </>
        )}
      </dl>
    </details>
  );
}
