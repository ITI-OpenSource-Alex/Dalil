import type { Metadata } from "next";
import {
  ArrowRight,
  Compass,
  Download,
  FileText,
  GraduationCap,
  Sparkles,
  Target,
} from "lucide-react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  EmptyState,
  Eyebrow,
  Heading,
  Icon,
  Progress,
  Skeleton,
  SkeletonGroup,
  Spinner,
  Text,
} from "@/components/ui";
import { InteractiveExamples } from "./interactive";

export const metadata: Metadata = {
  title: "Design System — GOA",
  description: "Living reference for GOA's UI primitives and design tokens.",
  robots: { index: false, follow: false },
};

/* This page is the living style guide: it renders every primitive in every
   variant and state, so regressions are visible rather than theoretical.
   It is noindex'd and unlinked from app navigation. */

function Section({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-border pt-10">
      <Heading as="h2" size="lg">
        {title}
      </Heading>
      {description && (
        <Text size="sm" tone="muted" className="mt-1.5 max-w-2xl">
          {description}
        </Text>
      )}
      <div className="mt-6">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-b border-border py-4 last:border-b-0 sm:flex-row sm:items-center sm:gap-6">
      <span className="w-40 shrink-0 text-sm font-medium text-fg-subtle">
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  );
}

function Swatch({
  name,
  className,
  note,
}: {
  name: string;
  className: string;
  note?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div
        className={`h-14 w-full rounded-card border border-border ${className}`}
      />
      <span className="font-mono text-xs text-fg">{name}</span>
      {note && <span className="text-xs text-fg-subtle">{note}</span>}
    </div>
  );
}

export default function DesignSystemPage() {
  return (
    <main id="main-content" className="min-h-screen bg-canvas">
      <div className="mx-auto flex max-w-5xl flex-col gap-10 px-6 py-16">
        <header className="flex flex-col gap-3">
          <Eyebrow>Internal reference</Eyebrow>
          <Heading as="h1" size="xl">
            GOA Design System
          </Heading>
          <Text tone="muted" measure>
            Every primitive, every variant, every state. Tokens are documented
            in <span className="font-mono text-sm">docs/DESIGN-TOKENS.md</span>.
          </Text>
        </header>

        {/* ============================================ Colour */}
        <Section
          id="colour"
          title="Colour"
          description="Components consume the semantic tokens below. The forest / sand / sage ramps underneath them are an escape hatch, not a default."
        >
          <div className="flex flex-col gap-8">
            <div>
              <Text size="sm" weight="semibold" className="mb-3">
                Surfaces &amp; lines
              </Text>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
                <Swatch name="canvas" className="bg-canvas" />
                <Swatch name="canvas-subtle" className="bg-canvas-subtle" />
                <Swatch name="canvas-inset" className="bg-canvas-inset" />
                <Swatch name="surface" className="bg-surface" />
                <Swatch name="surface-inverse" className="bg-surface-inverse" />
                <Swatch name="border-strong" className="bg-border-strong" />
              </div>
            </div>

            <div>
              <Text size="sm" weight="semibold" className="mb-3">
                Brand &amp; accent
              </Text>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
                <Swatch name="brand" className="bg-brand" note="#0d4d3a" />
                <Swatch name="brand-hover" className="bg-brand-hover" />
                <Swatch name="brand-muted" className="bg-brand-muted" />
                <Swatch name="brand-subtle" className="bg-brand-subtle" />
                <Swatch name="accent" className="bg-accent" />
                <Swatch name="accent-subtle" className="bg-accent-subtle" />
              </div>
            </div>

            <div>
              <Text size="sm" weight="semibold" className="mb-3">
                Status
              </Text>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Swatch name="success" className="bg-success" />
                <Swatch name="warning" className="bg-warning" />
                <Swatch name="danger" className="bg-danger" />
                <Swatch name="info" className="bg-info" />
              </div>
            </div>

            <div>
              <Text size="sm" weight="semibold" className="mb-3">
                Text tones — all pass WCAG AA on surface
              </Text>
              <div className="flex flex-col gap-1 rounded-card border border-border bg-surface p-5">
                <Text tone="default">fg — 15.9:1 — headings and body</Text>
                <Text tone="muted">fg-muted — 8.3:1 — secondary body</Text>
                <Text tone="subtle">fg-subtle — 6.0:1 — metadata, captions</Text>
              </div>
            </div>
          </div>
        </Section>

        {/* ============================================ Typography */}
        <Section
          id="typography"
          title="Typography"
          description="Serif (Fraunces) is applied only at display sizes. Sizes lg and up are serif; md and below are sans, because this app has headings that are 14px section labels."
        >
          <div className="flex flex-col gap-5 rounded-card border border-border bg-surface p-6">
            <Heading size="3xl">Display 3xl — hero only</Heading>
            <Heading size="2xl">Display 2xl — marketing sections</Heading>
            <Heading size="xl">Display xl — app page titles</Heading>
            <Heading size="lg">Display lg — subsections</Heading>
            <Heading size="md">Heading md — card titles (sans)</Heading>
            <Heading size="sm">Heading sm — small card titles (sans)</Heading>
            <Heading size="xs">Heading xs — section labels (sans)</Heading>
            <hr className="border-border" />
            <Text size="lg">Text lg — lead paragraphs and hero subcopy.</Text>
            <Text size="base" measure>
              Text base (16px) is the default body size. The audit found 294 of
              ~370 sizing declarations were text-sm or text-xs against 7 uses of
              text-base, which is the main reason the product read as dense.
            </Text>
            <Text size="sm" tone="muted">
              Text sm — dense UI, table cells, helper text.
            </Text>
            <Text size="xs" tone="subtle">
              Text xs — metadata and badges. Not a body size.
            </Text>
            <Eyebrow>Eyebrow — sits above a heading</Eyebrow>
          </div>
        </Section>

        {/* ============================================ Button */}
        <Section
          id="button"
          title="Button"
          description="Seven variants, three sizes. Default height is 44px, the WCAG 2.5.5 target size. Server-renderable: no client JS."
        >
          <div className="rounded-card border border-border bg-surface px-6">
            <Row label="Variants">
              <Button variant="primary">Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="danger">Danger</Button>
              <Button variant="link">Link</Button>
            </Row>
            <Row label="Inverse">
              <span className="flex items-center gap-3 rounded-card bg-surface-inverse p-3">
                <Button variant="inverse">On dark surface</Button>
                <Button variant="inverse" trailingIcon={ArrowRight}>
                  Get started
                </Button>
              </span>
            </Row>
            <Row label="Sizes">
              <Button size="sm">Small — 36px</Button>
              <Button size="md">Medium — 44px</Button>
              <Button size="lg">Large — 48px</Button>
            </Row>
            <Row label="With icons">
              <Button leadingIcon={Download}>Download</Button>
              <Button trailingIcon={ArrowRight}>Continue</Button>
              <Button variant="secondary" iconOnly aria-label="Download report">
                <Icon icon={Download} size="sm" />
              </Button>
            </Row>
            <Row label="Loading">
              <Button loading>Submitting</Button>
              <Button variant="secondary" loading>
                Saving changes
              </Button>
              <Button variant="danger" loading loadingLabel="Deleting account">
                Delete
              </Button>
            </Row>
            <Row label="Disabled">
              <Button disabled>Primary</Button>
              <Button variant="secondary" disabled>
                Secondary
              </Button>
              <Button variant="ghost" disabled>
                Ghost
              </Button>
            </Row>
            <Row label="Full width">
              <div className="w-full max-w-sm">
                <Button fullWidth trailingIcon={ArrowRight}>
                  Create your account
                </Button>
              </div>
            </Row>
            <Row label="asChild — link">
              <Button asChild trailingIcon={ArrowRight}>
                <a href="#button">Rendered as an anchor</a>
              </Button>
            </Row>
          </div>
        </Section>

        {/* ============================================ Badge */}
        <Section
          id="badge"
          title="Badge"
          description="Seven tones × three variants. Replaces six hand-written chip implementations."
        >
          <div className="rounded-card border border-border bg-surface px-6">
            <Row label="Subtle">
              <Badge tone="neutral">Neutral</Badge>
              <Badge tone="brand">Brand</Badge>
              <Badge tone="accent">Accent</Badge>
              <Badge tone="success">Success</Badge>
              <Badge tone="warning">Warning</Badge>
              <Badge tone="danger">Danger</Badge>
              <Badge tone="info">Info</Badge>
            </Row>
            <Row label="Solid">
              <Badge tone="brand" variant="solid">
                Most popular
              </Badge>
              <Badge tone="accent" variant="solid">
                New
              </Badge>
              <Badge tone="danger" variant="solid">
                Overdue
              </Badge>
            </Row>
            <Row label="Outline">
              <Badge tone="neutral" variant="outline">
                Soon
              </Badge>
              <Badge tone="brand" variant="outline">
                Band 7.5
              </Badge>
            </Row>
            <Row label="Sizes &amp; shape">
              <Badge size="sm">Small</Badge>
              <Badge size="md">Medium</Badge>
              <Badge size="lg">Large</Badge>
              <Badge pill tone="brand">
                Pill
              </Badge>
            </Row>
            <Row label="With dot / icon">
              <Badge tone="success" dot>
                Connected
              </Badge>
              <Badge tone="warning" dot>
                Recording
              </Badge>
              <Badge tone="brand" icon={Sparkles}>
                AI scored
              </Badge>
            </Row>
          </div>
        </Section>

        {/* ============================================ Forms */}
        <Section
          id="forms"
          title="Forms"
          description="Field owns every label, hint, error and ARIA relationship. The error below is announced via role=alert and linked with aria-describedby — neither existed anywhere in the codebase before."
        >
          <div className="rounded-card border border-border bg-surface p-6">
            <InteractiveExamples />
          </div>
        </Section>

        {/* ============================================ Card */}
        <Section
          id="card"
          title="Card"
          description="Four variants with assigned meaning, replacing the interchangeable use of shadow-2xs, shadow-sm and shadow-xl for the same role."
        >
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <Card variant="flat">
              <Heading as="h3" size="sm">
                Flat
              </Heading>
              <Text size="sm" tone="muted" className="mt-1">
                Default. Separation comes from the border, not a shadow.
              </Text>
            </Card>

            <Card variant="raised">
              <Heading as="h3" size="sm">
                Raised
              </Heading>
              <Text size="sm" tone="muted" className="mt-1">
                Resting elevation for content that floats above the canvas.
              </Text>
            </Card>

            <Card variant="interactive">
              <Heading as="h3" size="sm">
                Interactive
              </Heading>
              <Text size="sm" tone="muted" className="mt-1">
                Lifts on hover. Hover me — without it, a clickable card looks
                identical to a static one.
              </Text>
            </Card>

            <Card variant="inverse">
              <Heading as="h3" size="sm" tone="inverse">
                Inverse
              </Heading>
              <Text size="sm" tone="inverse-muted" className="mt-1">
                For CTA bands and dark panels.
              </Text>
            </Card>

            <Card padding="none" className="sm:col-span-2">
              <CardHeader>
                <CardTitle>Composed card</CardTitle>
                <CardDescription>
                  Header, body and a divided footer.
                </CardDescription>
              </CardHeader>
              <CardBody>
                <Text size="sm" tone="muted">
                  Use padding=&quot;none&quot; when composing, since the
                  subcomponents bring their own spacing.
                </Text>
              </CardBody>
              <CardFooter divided>
                <Button size="sm">Save</Button>
                <Button size="sm" variant="ghost">
                  Cancel
                </Button>
              </CardFooter>
            </Card>
          </div>
        </Section>

        {/* ============================================ Alert */}
        <Section
          id="alert"
          title="Alert"
          description="Danger announces assertively (role=alert); other tones announce politely (role=status). Absorbs three divergent error-banner implementations."
        >
          <div className="flex flex-col gap-4">
            <Alert tone="info" title="Your profile is still loading" announce="none">
              Chat will use a placeholder identity until this finishes.
            </Alert>
            <Alert tone="success" title="Checklist generated" announce="none">
              22 items across 4 phases are ready for TU Munich.
            </Alert>
            <Alert tone="warning" title="10 minutes remaining" announce="none">
              Your Reading section will submit automatically when time expires.
            </Alert>
            <Alert
              tone="danger"
              title="Couldn't start the exam"
              announce="none"
              actions={
                <>
                  <Button size="sm" variant="danger">
                    Try again
                  </Button>
                  <Button size="sm" variant="ghost">
                    Go back
                  </Button>
                </>
              }
            >
              The exam service didn&apos;t respond. Your progress has been saved.
            </Alert>
            <Alert tone="info" icon={null} announce="none">
              An alert with no icon and no title — for plain inline notes.
            </Alert>
          </div>
        </Section>

        {/* ============================================ Feedback */}
        <Section
          id="feedback"
          title="Progress, Skeleton &amp; Spinner"
          description="Progress requires an accessible label. Skeleton shimmers rather than pulses, because a fading block reads as broken."
        >
          <div className="flex flex-col gap-8">
            <div className="grid gap-6 sm:grid-cols-2">
              <Progress
                value={2}
                max={4}
                label="Onboarding progress"
                valueText="Step 2 of 4"
                showValue
              />
              <Progress
                value={68}
                label="Checklist completion"
                tone="success"
                showValue
              />
              <Progress value={40} label="Upload" tone="accent" size="sm" />
              <Progress value={92} label="Storage used" tone="warning" size="lg" />
            </div>

            <div className="grid gap-6 sm:grid-cols-2">
              <SkeletonGroup
                label="Loading profile"
                className="flex flex-col gap-3 rounded-card border border-border bg-surface p-5"
              >
                <div className="flex items-center gap-3">
                  <Skeleton shape="circle" className="h-10 w-10" />
                  <Skeleton className="h-4 w-32" />
                </div>
                <Skeleton shape="text" lines={3} />
              </SkeletonGroup>

              <SkeletonGroup
                label="Loading results"
                className="flex flex-col gap-3"
              >
                <Skeleton shape="block" className="h-24 w-full" />
                <Skeleton shape="block" className="h-12 w-full" />
              </SkeletonGroup>
            </div>

            <div className="flex items-center gap-6 rounded-card border border-border bg-surface p-5">
              <Spinner size="xs" />
              <Spinner size="sm" />
              <Spinner size="md" />
              <Spinner size="lg" className="text-brand" />
              <Text size="sm" tone="muted">
                Spinner — inherits currentColor.
              </Text>
            </div>
          </div>
        </Section>

        {/* ============================================ EmptyState */}
        <Section
          id="empty-state"
          title="Empty state"
          description="Instructional, not apologetic — nothing has gone wrong. An empty state without an action is a dead end."
        >
          <div className="grid gap-5 lg:grid-cols-2">
            <Card padding="none">
              <EmptyState
                icon={Compass}
                title="No opportunities yet"
                description="Complete your profile and GOA will rank Master's programmes by how well they fit."
                actions={
                  <>
                    <Button trailingIcon={ArrowRight}>Complete profile</Button>
                    <Button variant="ghost">Learn how matching works</Button>
                  </>
                }
              />
            </Card>
            <EmptyState
              bordered
              icon={FileText}
              size="sm"
              title="No checklists"
              description="Generate one from any matched programme."
              actions={<Button size="sm" variant="secondary">Browse programmes</Button>}
            />
          </div>
        </Section>

        {/* ============================================ Icon */}
        <Section
          id="icon"
          title="Icon"
          description="Four sizes with pinned stroke weights. Icons are aria-hidden unless given a label, so they aren't announced twice beside a visible one."
        >
          <div className="flex flex-wrap items-end gap-8 rounded-card border border-border bg-surface p-6">
            {(["xs", "sm", "md", "lg"] as const).map((size) => (
              <div key={size} className="flex flex-col items-center gap-2">
                <Icon icon={GraduationCap} size={size} className="text-brand" />
                <span className="font-mono text-xs text-fg-subtle">{size}</span>
              </div>
            ))}
            <div className="flex flex-col items-center gap-2">
              <span className="flex h-12 w-12 items-center justify-center rounded-card bg-brand-muted text-brand-fg">
                <Icon icon={Target} size="md" />
              </span>
              <span className="font-mono text-xs text-fg-subtle">tile</span>
            </div>
          </div>
        </Section>

        {/* ============================================ Elevation */}
        <Section
          id="elevation"
          title="Elevation &amp; radius"
          description="Forest-tinted shadows, not black. Radius is named by role so the choice is a decision rather than a habit."
        >
          {/* Class names are written out in full rather than interpolated:
              Tailwind scans source text for complete candidates, so
              `shadow-${level}` would generate nothing. */}
          <div className="grid gap-5 sm:grid-cols-4">
            {(
              [
                ["shadow-e1", "flex h-24 items-center justify-center rounded-card bg-surface shadow-e1"],
                ["shadow-e2", "flex h-24 items-center justify-center rounded-card bg-surface shadow-e2"],
                ["shadow-e3", "flex h-24 items-center justify-center rounded-card bg-surface shadow-e3"],
                ["shadow-e4", "flex h-24 items-center justify-center rounded-card bg-surface shadow-e4"],
              ] as const
            ).map(([name, cls]) => (
              <div key={name} className={cls}>
                <span className="font-mono text-xs text-fg-subtle">{name}</span>
              </div>
            ))}
          </div>
          <div className="mt-5 grid gap-5 sm:grid-cols-4">
            {(
              [
                ["rounded-chip · 6px", "flex h-24 items-center justify-center border border-border bg-canvas-subtle rounded-chip"],
                ["rounded-control · 10px", "flex h-24 items-center justify-center border border-border bg-canvas-subtle rounded-control"],
                ["rounded-card · 16px", "flex h-24 items-center justify-center border border-border bg-canvas-subtle rounded-card"],
                ["rounded-panel · 24px", "flex h-24 items-center justify-center border border-border bg-canvas-subtle rounded-panel"],
              ] as const
            ).map(([name, cls]) => (
              <div key={name} className={cls}>
                <span className="font-mono text-xs text-fg-subtle">{name}</span>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </main>
  );
}
