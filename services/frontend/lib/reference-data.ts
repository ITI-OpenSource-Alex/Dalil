/**
 * Reference lists for the wizard's and profile editor's searchable selects.
 *
 * Countries are stored and sent as their FULL NAME, not a short id. This is not
 * cosmetic: RAG filters candidate programmes with
 * `WHERE country = ANY($1::text[])` against a `country` column holding values
 * like 'Germany' and 'Netherlands' (services/rag/app/services/scoring.py,
 * app/migrations/029_seed_demo_programs.sql). The wizard previously persisted
 * the ids "us"/"de"/"eu" into `targetCountries`, which matched no row in that
 * table, so every profile that named a target country silently got *fewer*
 * matches than one that named none — an absent filter widens the search, a
 * wrong one empties it.
 *
 * STUDY_DESTINATIONS is deliberately led by the countries the catalogue
 * actually covers, with the rest kept so the field is not a lie about where a
 * user is allowed to want to study.
 */

export interface CountryOption {
  /** The value persisted to `targetCountries` — must match RAG's column. */
  name: string;
  /** ISO-3166 alpha-2, used only for the flag glyph. */
  code: string;
}

/** Countries with programmes in the seeded catalogue, listed first. */
export const CATALOGUE_COUNTRIES = [
  "Germany",
  "Netherlands",
  "Sweden",
  "Italy",
  "Switzerland",
] as const;

export const STUDY_DESTINATIONS: CountryOption[] = [
  { name: "Germany", code: "DE" },
  { name: "Netherlands", code: "NL" },
  { name: "Sweden", code: "SE" },
  { name: "Italy", code: "IT" },
  { name: "Switzerland", code: "CH" },
  { name: "Austria", code: "AT" },
  { name: "Belgium", code: "BE" },
  { name: "Denmark", code: "DK" },
  { name: "Finland", code: "FI" },
  { name: "France", code: "FR" },
  { name: "Ireland", code: "IE" },
  { name: "Norway", code: "NO" },
  { name: "Poland", code: "PL" },
  { name: "Portugal", code: "PT" },
  { name: "Spain", code: "ES" },
  { name: "Czechia", code: "CZ" },
  { name: "Estonia", code: "EE" },
  { name: "Hungary", code: "HU" },
  { name: "United Kingdom", code: "GB" },
  { name: "United States", code: "US" },
  { name: "Canada", code: "CA" },
  { name: "Australia", code: "AU" },
  { name: "New Zealand", code: "NZ" },
  { name: "Japan", code: "JP" },
  { name: "South Korea", code: "KR" },
  { name: "Singapore", code: "SG" },
  { name: "United Arab Emirates", code: "AE" },
  { name: "Turkey", code: "TR" },
];

/** True for a destination the seeded programme catalogue can actually match. */
export function hasCatalogueCoverage(countryName: string): boolean {
  return (CATALOGUE_COUNTRIES as readonly string[]).includes(countryName);
}

/**
 * Regional-indicator flag for a two-letter code. Purely decorative — every
 * call site also renders the country name, and this is aria-hidden.
 */
export function flagEmoji(code: string): string {
  return code
    .toUpperCase()
    .replace(/./g, (char) =>
      String.fromCodePoint(127397 + char.charCodeAt(0)),
    );
}

/**
 * Fields of study offered as suggestions. The combobox they feed accepts free
 * text as well: RAG maps this onto a discipline slug by substring match
 * (`discipline_for_field_of_study`) and treats an unrecognised value as "no
 * discipline filter" rather than "no results", so an unlisted field is safe.
 */
export const FIELDS_OF_STUDY = [
  "Computer Science",
  "Software Engineering",
  "Artificial Intelligence",
  "Data Science",
  "Cybersecurity",
  "Information Systems",
  "Electrical Engineering",
  "Electronics Engineering",
  "Mechanical Engineering",
  "Mechatronics",
  "Robotics",
  "Civil Engineering",
  "Chemical Engineering",
  "Biomedical Engineering",
  "Industrial Engineering",
  "Aerospace Engineering",
  "Environmental Engineering",
  "Materials Science",
  "Mathematics",
  "Statistics",
  "Physics",
  "Chemistry",
  "Biology",
  "Biotechnology",
  "Medicine",
  "Pharmacy",
  "Public Health",
  "Architecture",
  "Urban Planning",
  "Business Administration",
  "Finance",
  "Accounting",
  "Economics",
  "Marketing",
  "Supply Chain Management",
  "Law",
  "International Relations",
  "Political Science",
  "Psychology",
  "Sociology",
  "Education",
  "Linguistics",
  "Journalism",
  "Graphic Design",
  "Fine Arts",
];

/**
 * Universities offered as suggestions, led by the institutions in the seeded
 * catalogue. Free text is accepted — this field is wizard-local context and is
 * not sent to the backend at all (UpdateProfileDto has no `university`).
 */
export const UNIVERSITIES = [
  "Technical University of Berlin",
  "Technical University of Munich",
  "RWTH Aachen University",
  "Vrije Universiteit Amsterdam",
  "University of Twente",
  "Delft University of Technology",
  "KTH Royal Institute of Technology",
  "Politecnico di Milano",
  "ETH Zurich",
  "University of Amsterdam",
  "Ludwig Maximilian University of Munich",
  "Heidelberg University",
  "Uppsala University",
  "Lund University",
  "University of Copenhagen",
  "Aalto University",
  "KU Leuven",
  "University of Vienna",
  "Sorbonne University",
  "University of Oxford",
  "University of Cambridge",
  "Imperial College London",
  "University College London",
  "University of Edinburgh",
  "University of Manchester",
  "Cairo University",
  "Ain Shams University",
  "Alexandria University",
  "American University in Cairo",
  "German University in Cairo",
  "Nile University",
  "Zagazig University",
  "Mansoura University",
  "Massachusetts Institute of Technology",
  "Stanford University",
  "University of Toronto",
  "University of British Columbia",
  "University of Melbourne",
  "National University of Singapore",
];

export const DEGREE_LEVELS = [
  { value: "Bachelors", label: "Bachelor's degree" },
  { value: "Masters", label: "Master's degree" },
  { value: "PhD", label: "Ph.D. / Doctorate" },
  { value: "Diploma", label: "Diploma / Other" },
] as const;

export const TARGET_DEGREE_LEVELS = DEGREE_LEVELS.filter(
  (d) => d.value !== "Diploma",
);

/**
 * Intake terms, generated rather than hardcoded so the list does not silently
 * rot into offering only past intakes the way a literal ["Fall 2026", ...]
 * array does.
 */
export function intakeOptions(now: Date = new Date()): string[] {
  const year = now.getFullYear();
  // Past the northern-hemisphere autumn deadline season, the current year's
  // Fall intake is no longer a realistic first option.
  const startYear = now.getMonth() >= 9 ? year + 1 : year;
  const terms: string[] = [];
  for (let offset = 0; offset < 3; offset += 1) {
    terms.push(`Fall ${startYear + offset}`);
    terms.push(`Spring ${startYear + offset + 1}`);
  }
  terms.push("Still deciding");
  return terms;
}
