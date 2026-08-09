import { ChevronDown } from "lucide-react";
import { Icon, Text } from "@/components/ui";
import { Container, Section, SectionHeader } from "./section";
import { Reveal } from "./reveal";

/* ------------------------------------------------------------------ *
 * Built on native <details>/<summary>.
 *
 * That buys keyboard operation, correct expanded/collapsed announcement,
 * find-in-page that opens the matching panel, and it works with JS
 * disabled -- all for zero bytes. A custom accordion would reimplement
 * every one of those and ship JS onto the marketing bundle to do it.
 *
 * The questions are the real objections, answered plainly. The band-score
 * answer in particular is deliberately unglamorous: overstating what an
 * LLM's IELTS scoring means would undermine the section's whole purpose.
 * ------------------------------------------------------------------ */

const FAQS = [
  {
    q: "Is the free plan actually free?",
    a: "Yes. Opportunity matching, confidence scoring, application checklists and chat are free with no time limit and no card. Pro ($20/month) adds the IELTS exam simulations and AI band scoring — that is the only paid part.",
  },
  {
    q: "How accurate is the AI band scoring?",
    a: "It is guidance, not an official result. Dalil scores Writing and Speaking against the public IELTS band descriptors and explains its reasoning line by line, which is useful for finding weaknesses and tracking progress between attempts. It is not affiliated with the IELTS test owners and cannot predict your exam-day score.",
  },
  {
    q: "Which countries and programmes are covered?",
    a: "English-taught Master's programmes and scholarships across Europe, with the strongest coverage in Germany, the Netherlands, Sweden, Denmark, France, Ireland, Finland and Norway. Coverage grows as new programme data is indexed.",
  },
  {
    q: "How does the matching actually work?",
    a: "Dalil compares your academic profile — degree, GPA, ECTS credits, language scores, work experience — against each programme's published entry requirements, and returns a confidence score with the factors behind it. It is a computed fit against stated requirements, not a keyword search and not a prediction of an admissions decision.",
  },
  {
    q: "What do you do with my CV and personal data?",
    a: "Your CV is used to fill in your profile, and your profile is used to rank programmes and generate checklists. You can delete everything Dalil has stored about you at any time from the chat screen, which removes both your saved profile facts and your conversation history.",
  },
  {
    q: "Do I need an IELTS score before I start?",
    a: "No. Matching works without one — Dalil will show you which programmes are within reach and what band each requires, so you know the target before you book a test.",
  },
];

export function FAQ() {
  return (
    <Section id="faq" tone="canvas" labelledBy="faq-heading">
      <Container>
        <SectionHeader
          id="faq-heading"
          align="center"
          eyebrow="Questions"
          title="The things people ask before signing up"
        />

        <div className="mx-auto mt-14 max-w-3xl">
          <div className="divide-y divide-border overflow-hidden rounded-card border border-border bg-surface">
            {FAQS.map((faq, i) => (
              <Reveal key={faq.q} delay={i * 50}>
                <details className="group">
                  <summary
                    className={
                      "flex cursor-pointer list-none items-center justify-between gap-6 px-6 py-5 " +
                      "transition-colors duration-120 ease-out hover:bg-canvas-subtle " +
                      "[&::-webkit-details-marker]:hidden"
                    }
                  >
                    <span className="text-base font-semibold text-fg">
                      {faq.q}
                    </span>
                    <Icon
                      icon={ChevronDown}
                      size="sm"
                      className="shrink-0 text-fg-subtle transition-transform duration-200 ease-out group-open:rotate-180"
                    />
                  </summary>

                  <div className="px-6 pb-5">
                    <Text size="sm" tone="muted" className="max-w-2xl">
                      {faq.a}
                    </Text>
                  </div>
                </details>
              </Reveal>
            ))}
          </div>

          <Reveal delay={120}>
            <p className="mt-8 text-center text-sm text-fg-subtle">
              Still have a question?{" "}
              <a
                href="mailto:hello@goa.app"
                className="font-medium text-brand-fg underline underline-offset-4 decoration-brand-border transition-colors duration-120 hover:decoration-brand-fg"
              >
                Email us
              </a>{" "}
              and a human will answer.
            </p>
          </Reveal>
        </div>
      </Container>
    </Section>
  );
}
