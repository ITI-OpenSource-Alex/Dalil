import { Container, Section } from "./section";
import { Reveal } from "./reveal";

/* ------------------------------------------------------------------ *
 * The credibility strip that normally holds a logo wall.
 *
 * It deliberately does NOT show university logos. GOA indexes these
 * institutions' public programme data; it is not partnered with them, and
 * a row of university crests under the hero would imply endorsement that
 * does not exist. Naming the destination countries makes the same point
 * -- "this covers the places I am considering" -- and is true.
 *
 * If real partnerships or press coverage ever exist, this is the section
 * they belong in.
 * ------------------------------------------------------------------ */

const COUNTRIES = [
  "Germany",
  "Netherlands",
  "Sweden",
  "Denmark",
  "France",
  "Ireland",
  "Finland",
  "Norway",
];

export function TrustBar() {
  return (
    <Section tone="canvas" size="tight" className="border-y border-border">
      <Container>
        <Reveal className="flex flex-col items-center gap-5 text-center">
          <p className="text-xs font-semibold tracking-[0.08em] text-fg-subtle uppercase">
            Master&apos;s programmes and scholarships across Europe
          </p>

          <ul className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
            {COUNTRIES.map((country) => (
              <li
                key={country}
                className="font-serif text-lg font-semibold text-fg-muted/70 transition-colors duration-200 ease-out hover:text-fg-muted"
              >
                {country}
              </li>
            ))}
          </ul>
        </Reveal>
      </Container>
    </Section>
  );
}
