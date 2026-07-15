# The Last Dance

**Board URL:** https://trello.com/b/gBzYDiLL/the-last-dance

*Exported from Trello JSON — 43 open cards across 10 lists.*

## Table of Contents

- [TODO Backend](#todo-backend) (3)
- [TODO Frontend](#todo-frontend) (0)
- [TODO CI/CD](#todo-cicd) (0)
- [TODO Infra](#todo-infra) (0)
- [TODO AI](#todo-ai) (0)
- [TODO Data](#todo-data) (2)
- [Blocked By Dependency](#blocked-by-dependency) (4)
- [In Progress](#in-progress) (7)
- [Pending Review](#pending-review) (1)
- [Done](#done) (26)

---

## TODO Backend

### GOA-052 — Speaking exam mode — holistic Part 1/2/3 evaluation with post-exam feedback

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/jHJHWOzh

| | |
|---|---|
| **Service** | Exam |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P2 |
| **Story points** | 2 |
| **Dependencies** | GOA-013 (Sprint 2) — Speaking swarm — 4 IELTS evaluation agents (Fluency, Lexical, Grammar, Pronunciation) with metrics; GOA-048 (Sprint 1) — Exam service scaffold — FastAPI + exam_db + Academic/General split; GOA-049 (Sprint 1) — Cambridge IELTS content ingestion — Reading and Listening question banks |

**Summary:** IELTS exam mode for Speaking. Strict Part 1/2/3 structure with Cambridge prompts. NO feedback during the exam — transcripts stored silently after each part. Holistic 4-agent evaluation runs only after Part 3 is submitted, giving the agents full context across all 3 parts. Results shown with per-criterion bands, per-part narrative, and specific transcript examples.

**Acceptance criteria:**

- GET /exam/speaking/start accepts {examType: academic|general} — returns session with Part 1 questions (4-5 general), Part 2 cue card (topic + bullet points), Part 3 questions (4-5 discussion)
- All questions sourced from Cambridge IELTS books stored in exam_db — random unseen selection per user
- Part 2: server sets 60s prep timer then 120s speaking timer. Client enforces visually, server validates on submit
- Evaluation reuses existing 4-agent Speaking swarm (GOA-013): Fluency, Lexical, Grammar, Pronunciation
- Overall Speaking band = mean of 4 criteria rounded to nearest 0.5
- ExamResult stored in exam_db with skillArea=speaking, linked to exam session_id
- Result: overall_band, per_criterion bands, per_part transcripts, full feedback per criterion
- NO feedback or score shown after Part 1 or Part 2 — only a silent 'Part N complete' confirmation so the user cannot adjust their performance based on interim scores
- After each part: transcript stored in exam_db ExamSpeakingTranscript table {session_id, part (1|2|3), transcript_text, duration_s, question_text}
- After Part 3 submitted: Exam service sends all 3 transcripts + part prompts to Speaking service POST /evaluate/holistic
- Each of the 4 agents (Fluency/Lexical/Grammar/Pronunciation) receives the full concatenated context — all 3 transcripts with part labels — and evaluates holistically across the whole exam
- Agent response schema extended with part_notes: {part1: str, part2: str, part3: str} — narrative of performance per part for that criterion, and examples: [{part: int, quote: str, issue: str}] — specific transcript quotes with annotations
- Loading state shown to user during evaluation: 'Evaluating your exam...' spinner — target evaluation time P95 under 8 seconds (4 parallel agents on ~1500 token input)
- Results page sections: (1) Overall band prominently displayed, (2) 4 criterion bands with progress bars, (3) Per-criterion card showing overall feedback + per-part narrative + highlighted transcript examples, (4) Improvement tips per criterion linking to specific practice resources
- Results stored in exam_db ExamResult with full agent_responses JSON including part_notes and examples
- goa_speaking_exam_evaluations_total Prometheus counter, goa_speaking_exam_evaluation_ms histogram — target P95 under 8000ms

**Implementation notes:**

Exam service creates session with question set. Client connects to Speaking WebSocket with exam_session_id query param. Speaking service validates session via Exam service internal API before starting. Results POST back to Exam service.

**Tests / Definition of done:**

- Unit: Part 2 timing validation rejects submission if speak duration under 60s
- Integration: full 3-part speaking session, evaluation result stored in exam_db with correct structure
- Unit: transcript stored after each part without triggering evaluation
- Unit: holistic evaluation endpoint receives all 3 transcripts concatenated with correct part labels
- Unit: agent response parser correctly extracts part_notes and examples arrays
- Integration: complete full 3-part exam — verify no feedback shown mid-exam, results page shows per-part narrative with transcript quotes after Part 3

---

---

### GOA-087 — CV Processor Lambda — text and structured field extraction

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/w6Vompzl

| | |
|---|---|
| **Service** | Writing |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-089 (Sprint 2) — CV upload endpoint (writes the S3 object that triggers extraction); GOA-008 (Sprint 1) — Writing service scaffold; GOA-002 (Sprint 1) — Shared event schema contracts package |

**Summary:** Build the CV Processor worker that extracts text and structured fields from an uploaded CV. GOA-089 receives the CV file and writes it to S3 under `cvs/{userId}/`; this ticket is the extraction step triggered by that S3 write. The onboarding wizard, the CV review agent (GOA-025), and the Orchestration CV flow all assume a CV's text and structured fields already exist in `writing_db` — but no ticket produces them. This handler downloads the file, extracts plain text, extracts structured fields via an LLM, persists both to `writing_db`, and publishes `CVProcessed`.

**Context — why this is a separate ticket:**

CV upload (GOA-089) only receives the file and stores it in S3 — it does no extraction. The system workflow, however, depends on extracted CV data in several places:
- Onboarding Step 2d uploads the CV via GOA-089; the user proceeds without waiting while extraction runs in the background.
- GOA-025 (CV review agent) states it "reuses extraction logic from GOA-008" — that logic does not exist until this ticket.
- Orchestration's CV_REVIEW flow retrieves "already-extracted CV text from `writing_db`."

GOA-072 and GOA-031 provision and migrate the `cv-processor` Lambda *infrastructure*, but neither writes the handler. This ticket is that handler.

**Acceptance criteria:**

- Worker handler at `services/writing/cv_processor/handler.py` — invoked by S3 `ObjectCreated` events under the `cvs/` prefix in the `goa-writing-files` bucket (in local dev, by a LocalStack S3 notification; in staging/prod, by the Lambda provisioned in GOA-072)
- On invocation: download the object from S3, detect type, extract plain text — `pdfplumber` for PDF, `python-docx` for DOCX. Unsupported types (images, .exe, .txt-as-CV) → mark `status = failed`, log, do not crash
- Structured field extraction via Claude `claude-haiku-4-5-20251001` with structured output: `{name, email, phone, degree, institution, graduation_year, field_of_study, skills: [], work_experience: [{title, org, years}], languages: []}`
- Persist to `writing_db` `cv_reviews` table: `id, user_id, s3_key, extracted_text, structured_data (JSONB), status (pending|processing|ready|failed), error_message, processed_at`
- Publish `CVProcessed` event to SQS on completion. Payload: `{type: "CVProcessed", userId, cvId, s3Key, status (ready|failed)}` — added to the shared contracts package (GOA-002 already lists `CVProcessed`)
- Idempotency: skip if an object with the same `s3_key` + content hash is already `ready` — prevents duplicate LLM spend on S3 retries
- Max file size 10 MB enforced before download (read S3 object metadata first)
- Langfuse trace on the structured-extraction LLM call: `model, input_tokens, output_tokens, latency_ms, cost_usd, fields_extracted`
- `goa_cv_extraction_duration_ms` Prometheus histogram; `goa_cv_extraction_total` counter with label `outcome (success|fail|skipped)`
- Structured JSON log per invocation: `{userId, cvId, file_type, text_length, fields_extracted, duration_ms, outcome}`

**Downstream ticket impacts:**

- **GOA-072 / GOA-031**: both currently specify the cv-processor S3 trigger on the `essays/` prefix. This is incorrect — essays are typed text stored directly in `writing_db` (GOA-008) and are never extracted. CVs are stored under `cvs/`. The trigger prefix must be corrected from `essays/` to `cvs/` in both tickets.
- **GOA-025** (CV review agent): "reuses extraction logic from GOA-008" should now read "reuses extraction from GOA-087" — the extracted text and `structured_data` are read from `cv_reviews`, not re-extracted
- **GOA-002**: confirm `CVProcessed` event payload matches the schema above
- **GOA-077** (onboarding): Step 4 "Processing…" state is driven by polling CV status until `ready` — backed by this handler

**Implementation notes:**

Same Docker image as the Writing service with an overridden entrypoint, packaged as a container image Lambda (consistent with GOA-031). `pdfplumber` and `python-docx` added to the Writing service requirements. Structured extraction prompt is strict JSON-mode; on parse failure retry once then mark `failed`. S3 access via `boto3` (LocalStack endpoint in dev). The `cv_reviews` table is created by the Writing service's own migration set — add `extracted_text`, `structured_data`, `status`, `error_message`, `processed_at` columns if not already present.

**Tests / Definition of done:**

- Unit: `pdfplumber` path extracts text from a sample PDF CV fixture; `python-docx` path extracts from a DOCX fixture
- Unit: structured extraction returns all expected fields from sample CV text (LLM mocked)
- Unit: unsupported file type → `status = failed`, no exception raised
- Unit: file > 10 MB rejected before download
- Integration: upload a PDF to `cvs/{userId}/` in LocalStack S3 → handler invoked → `cv_reviews` row created with non-empty `extracted_text` and `structured_data`
- Integration: `CVProcessed` event published to SQS after extraction with `status = ready`
- Integration: re-deliver the same S3 event → second run is skipped (idempotent), no second LLM call (mock counter)

---

---

### GOA-020 — End-to-end evaluation suite — RAG retrieval quality and agent scoring accuracy(blocked by )

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/7sK7N2Jp

| | |
|---|---|
| **Service** | QA |
| **Type** | Test/Eval |
| **Language(s)** | Python, TypeScript, Go |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-012 (Sprint 2) — Profile Matcher Agent — 3-stage scoring pipeline; GOA-013 (Sprint 2) — Speaking swarm — 4 IELTS evaluation agents (Fluency, Lexical, Grammar, Pronunciation) with metrics; GOA-014 (Sprint 2) — Writing swarm — 4 evaluation agents (Task Response, Cohesion, Vocabulary, Grammar) with metrics; GOA-015 (Sprint 2) — Real data source adapters — IELTS, universities, scholarships |

**Summary:** Build an automated evaluation framework that measures RAG retrieval quality and scoring accuracy against a golden dataset. This runs in CI and blocks deployment on quality regression.

**Acceptance criteria:**

- Golden dataset: 50 question-answer pairs covering IELTS, universities, scholarships, visa requirements — stored in /evals/golden_dataset.json
- RAG eval: for each question, retrieve top-5 chunks, check if correct answer is derivable — target: >80% pass rate
- Scoring eval: 20 synthetic profiles with known expected outcomes (blocked, low, mid, high) — target: 100% correct gate decisions, ±5 points on soft scores
- Speaking eval: 10 sample transcripts with expert-assigned bands — LLM agent bands within ±0.5 of expert: >80% pass rate
- Writing eval: 5 sample essays with expert-assigned bands — same threshold
- All evals produce a report: evals/reports/{timestamp}.json with per-question results
- GitHub Actions step runs evals on every PR to main — fails if any metric drops below threshold
- Report includes: per-question accuracy, aggregate pass rate, comparison vs previous run (regression detection)
- Eval metrics stored as JSON artefact in CI — enables trend tracking across PRs
- Eval report JSON schema includes: {run_id, timestamp, git_sha, metrics: {rag_accuracy, gate_accuracy, scoring_mae, speaking_accuracy, writing_accuracy}, per_question: [...], regression_vs_previous: {delta_rag, delta_speaking, delta_writing}}
- CI step uploads report JSON to S3 at evals/reports/{git_sha}.json after every run for historical tracking
- CI step exits 1 and prints regression diff if any metric drops >5% vs the previous report fetched from S3
- GitHub Actions posts a PR comment with eval summary table: metric name, current value, target, delta, pass or fail badge

**Implementation notes:**

Python eval runner script. LLM-as-a-Judge for RAG quality (Claude evaluates if answer is correct). Deterministic checks for scoring gates. Expert band annotations stored in golden dataset. Report includes per-question breakdown and aggregate metrics.

**Tests / Definition of done:**

- Eval runner completes without error on fixture data
- Gate decisions 100% correct on synthetic profiles
- Report JSON schema validates correctly
- CI: introduce deliberate regression in golden dataset then verify PR comment shows failing badge with correct delta
- CI: successful run uploads report to S3 and post PR comment with all-pass badges

---

---

## TODO Frontend

*No cards.*

## TODO CI/CD

*No cards.*

## TODO Infra

*No cards.*

## TODO AI

*No cards.*

## TODO Data

### GOA-086 — Egyptian applicant visa requirements — structured data + ingestion adapters

**Members:** Ahmed Dorgham · **Link:** https://trello.com/c/xxUDfK6t

| | |
|---|---|
| **Service** | RAG + Ingestion |
| **Type** | Data |
| **Language(s)** | Python |
| **Priority** | P2 |
| **Story points** | 5 |
| **Dependencies** | GOA-006 (Sprint 1) — RAG service scaffold; GOA-010 (Sprint 1) — Ingestion worker scaffold; GOA-015 (Sprint 2) — Real data source adapters |

**Summary:** Add a `visa_requirements` structured table to `rag_db` capturing visa application rules as they apply specifically to Egyptian applicants. The existing `documents` table stores visa content as unstructured chunks — insufficient for precise questions like "Do I need an APS certificate to apply to Germany?" or "How do I open a blocked account from Egypt?" This ticket adds structured, queryable visa data, financial requirements with Egypt-specific banking context, and the ingestion adapters to populate both from embassy and visa centre sources.

**Context — why Egypt-specific:**

Egyptian applicants face requirements that do not appear in generic visa guides targeted at European applicants:

- **APS certificate** (Akademische Prüfstelle Cairo) — mandatory for Egyptian students applying to German universities. Not mentioned on German university websites; issued only by the APS office in Cairo.
- **Campus France Egypt** — France requires Egyptian students to pre-register through Campus France Cairo before a student visa can be issued. This step does not exist for most other nationalities.
- **Military status certificate** — required for Egyptian male applicants under 30 for multiple Schengen countries.
- **Blocked account (Sperrkonto)** — Germany requires ~€11,208/year in a blocked account. Egyptian applicants cannot freely transfer large EGP amounts to EUR due to Central Bank of Egypt capital controls. Fintiba and Expatrio are the two main blocked account providers; both accept Egyptian debit cards for setup but have different fee structures and processing timelines relevant to Egyptians.
- **Proof of funds in EGP context** — embassies specify requirements in EUR/GBP/CAD; EGP exchange rate volatility makes this a frequently updated question.
- **VFS Global Egypt** — handles biometric appointments for most Schengen countries, UK, and Canada in Egypt. Appointment wait times and centre locations (Cairo, Alexandria) are common questions.
- **Thanaweya Amma recognition** — each destination country handles Egyptian secondary credentials differently (WES evaluation for Canada, anabin database for Germany, NARIC for UK, "Dichiarazione di Valore" / Declaration of Value for Italy — issued by the Italian Embassy Cairo, a required foreign-degree recognition step with no equivalent for most other nationalities).
- **Egyptian Police Criminal Record Certificate** — required by most destinations, must be apostilled and translated.

**Acceptance criteria:**

- New `visa_requirements` table in `rag_db`:
  ```sql
  CREATE TABLE visa_requirements (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country           VARCHAR(100) NOT NULL,
    visa_type         VARCHAR(100) NOT NULL,       -- 'student', 'work', 'job-seeker'
    issuing_body      VARCHAR(200) NOT NULL,       -- 'German Embassy Cairo', 'VFS Global Egypt - French'
    source_url        VARCHAR(500) NOT NULL,
    egyptian_specific BOOLEAN NOT NULL DEFAULT TRUE,
    requirements      JSONB NOT NULL,              -- structured list of required documents
    proof_of_funds    JSONB,                       -- see schema below
    processing_days_min INTEGER,
    processing_days_max INTEGER,
    notes             TEXT,
    last_scraped_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash      VARCHAR(64) NOT NULL,
    UNIQUE (country, visa_type, issuing_body)
  );
  ```
- `proof_of_funds` JSONB column schema:
  ```json
  {
    "amount_eur": 11208,
    "accepted_account_types": ["blocked_account", "personal_savings", "sponsor_letter"],
    "blocked_account_providers": [
      {"name": "Fintiba", "url": "fintiba.com", "setup_fee_eur": 89, "accepts_egyptian_debit": true},
      {"name": "Expatrio", "url": "expatrio.com", "setup_fee_eur": 69, "accepts_egyptian_debit": true}
    ],
    "minimum_balance_period_days": 90,
    "sponsor_letter_accepted": true,
    "notes_egypt": "CIB and QNB Egypt both issue certified bank statements accepted by the German Embassy Cairo. Capital controls apply — consult your bank before initiating EUR transfers."
  }
  ```
- Migration file `007_add_visa_requirements.sql` added to RAG service migrations, runs after existing migrations
- `GermanEmbassyCairoAdapter` — scrapes `cairo.diplo.de` for student visa required documents, APS certificate instructions, blocked account requirements, and proof of funds amounts
- `APSCairoAdapter` — scrapes `aps-egypt.de` for APS certificate procedure, required documents, processing time (currently 6–8 weeks), and fee in EGP
- `CampusFranceEgyptAdapter` — scrapes `egypte.campusfrance.org` for French student visa pre-registration steps, required documents, proof of funds requirements, and Campus France interview process
- `UKVISAEgyptAdapter` — scrapes `gov.uk/student-visa` for Egyptian-applicant requirements + VFS Global Egypt Cairo/Alexandria centre addresses and appointment booking URL
- `VFSGlobalEgyptAdapter` (Playwright — JS-rendered) — scrapes VFS Global Egypt portal for biometric appointment availability and centre details for Schengen countries (France, Netherlands, Italy, Austria, Belgium)
- `FintibaSperrkonto­Adapter` — scrapes `fintiba.com` for blocked account setup steps, fee schedule, processing time, and Egypt-specific payment instructions
- `CzechEmbassyCairoAdapter` — scrapes the Czech Embassy Cairo site (mzv.cz/cairo — verify exact URL at implementation time) for Egyptian-applicant student visa requirements, document checklist, processing times, **and the Czech Republic's published minimum financial-means requirement** populated into `proof_of_funds` (verify current figure at implementation time). Second half of the Poland/Hungary (GOA-015) + Czech/Spain/Italy (here) CEE/Spain/Italy expansion — these three get the Egypt-specific visa treatment rather than general program adapters, since GOA-015 already covers general program/scholarship listings for Poland and Hungary
- `SpainVisaEgyptAdapter` — scrapes the Spanish Embassy/Consulate Cairo student visa page (exteriores.gob.es — verify exact URL at implementation time) for Egyptian-applicant requirements, document checklist, **and Spain's published minimum means-of-subsistence requirement** (commonly IPREM-linked — verify current figure and reference basis at implementation time) populated into `proof_of_funds`. This is the adapter most directly answering "Spain has low study costs" myth questions — Spain's low/free public-university tuition is frequently misread as "no cost," when a monthly financial-means figure is still required for the visa itself
- `ItalyEmbassyCairoAdapter` — scrapes the Italian Embassy Cairo site (ambilcairo.esteri.it — verify exact URL at implementation time) for Egyptian-applicant student visa requirements, document checklist, processing times, the "Dichiarazione di Valore" (Declaration of Value) foreign-degree recognition procedure, **and Italy's published minimum means-of-subsistence requirement** populated into `proof_of_funds` (verify current figure and consular practice at implementation time — Italy's exact figure/reference basis varies by consulate). Italy's equivalent bureaucratic quirk to Germany's APS certificate is the Declaration of Value. Note: `VFSGlobalEgyptAdapter` above already covers Italy's Schengen biometric appointment logistics — this adapter fills the missing embassy-requirements/document-checklist/financial layer, same split as the Czech/Spain adapters
- Each adapter upserts into `visa_requirements` via RAG service internal endpoint `POST /internal/visa-requirements`, keyed by `(country, visa_type, issuing_body)` — idempotent on re-run
- All adapters also produce chunked `Document` objects upserted to the `documents` table via the standard ingestion pipeline — both structured and unstructured paths run in parallel
- All 9 adapters registered in `ingestion_sources` table with `scrape_frequency = 'monthly'` and `category = 'visa'`
- `POST /internal/visa-requirements` internal endpoint added to RAG service
- FAQ seed entries added to `faq_entries` for the 6 most common Egypt-specific questions:
  - "Do I need an APS certificate to study in Germany?"
  - "How do I apply for a French student visa from Egypt?"
  - "How do I open a blocked account (Sperrkonto) from Egypt?"
  - "How much money do I need for a German student visa?"
  - "Where is the VFS appointment centre in Egypt?"
  - "Does my Egyptian bank statement need to be translated for a visa application?"
- GOA-015's own adapters (IELTS.org, MastersPortal, DAAD, Chevening, plus the Poland/Hungary additions) are general program/scholarship sources, not visa-specific — they remain unchanged. There is no pre-existing gov.uk/make-it-in-germany.com/canada.ca adapter from GOA-015; `UKVISAEgyptAdapter` above is this ticket's own Egypt-specific coverage of UK visa requirements, and Canada has no visa adapter in the project yet

**Downstream ticket impacts:**

- **GOA-006**: `database.py` schema initialisation list must include migration `007_add_visa_requirements.sql`
- **GOA-015**: `ingestion_sources` seed data must include the 9 new adapters from this ticket (6 original + CzechEmbassyCairoAdapter + SpainVisaEgyptAdapter + ItalyEmbassyCairoAdapter)
- **GOA-012** (Profile Matcher): `visa_requirements` can now surface as a soft flag — if user profile has `military_status = 'deferred'`, add a note to the gap report that Germany and France student visas require a military status certificate
- **GOA-020** (Eval suite): golden dataset should include at least 5 Egypt-specific visa questions to validate retrieval quality on this content
- **GOA-018** (RAG Q&A): `/query` responses for visa questions now prefer structured `visa_requirements` rows for document checklist answers and fall back to `documents` chunks for narrative answers

**Implementation notes:**

Static embassy sites (`cairo.diplo.de`, `aps-egypt.de`, `egypte.campusfrance.org`, `gov.uk`, and the new Czech/Spain/Italy embassy sites) use `httpx` + `BeautifulSoup` — no Playwright needed. VFS Global Egypt and Fintiba are JS-rendered — use Playwright for those two adapters only. All adapters must handle Arabic content gracefully (skip, do not error). Add 2–3 second delay between requests per adapter. Handle HTTP 429 / 503 with exponential backoff.

**Tests / Definition of done:**

- Unit: `GermanEmbassyCairoAdapter` correctly parses APS certificate requirement and `proof_of_funds.amount_eur` from fixture HTML
- Unit: `APSCairoAdapter` extracts processing time and fee from fixture page
- Unit: `CampusFranceEgyptAdapter` extracts proof-of-funds amount and pre-registration step count from fixture page
- Unit: `FintibaSperrkonto­Adapter` extracts setup fee and `accepts_egyptian_debit` flag correctly
- Unit: `CzechEmbassyCairoAdapter`, `SpainVisaEgyptAdapter`, and `ItalyEmbassyCairoAdapter` each extract a document checklist and processing time from fixture HTML
- Unit: `ItalyEmbassyCairoAdapter` correctly extracts the Declaration of Value procedure as a distinct requirement, not conflated with the general document checklist
- Unit: `SpainVisaEgyptAdapter` and `ItalyEmbassyCairoAdapter` each populate `proof_of_funds` with their respective financial-means figure from fixture HTML
- Integration: run all 9 adapters in dry-run mode — verify 9+ rows would be upserted to `visa_requirements`
- Integration: `POST /internal/visa-requirements` upserts a row; re-running the same payload is idempotent (no duplicate rows, `last_scraped_at` updated)
- Integration: `POST /query` with "Do I need an APS certificate for Germany?" returns an answer citing `cairo.diplo.de` or `aps-egypt.de` as source
- Integration: `POST /query` with "How do I open a blocked account from Egypt?" returns answer mentioning Fintiba or Expatrio
- Integration: FAQ hit for "APS certificate" question returns cached answer without an LLM call (`hit_count` increments on `faq_entries` row)

---

---

### GOA-088 — Structured opportunity ingestion — program_requirements and scholarship_programs tables

**Members:** Ahmed Dorgham · **Link:** https://trello.com/c/DKjUtlCL

| | |
|---|---|
| **Service** | Ingestion |
| **Type** | Data |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-006 (Sprint 1) — RAG service scaffold; GOA-010 (Sprint 1) — Ingestion worker scaffold; GOA-015 (Sprint 2) — Real data source adapters |

**Summary:** The scoring and matching pipeline runs on structured data, but the ingestion pipeline only produces unstructured vector chunks. GOA-012 (Profile Matcher) reads `program_requirements` for hard gates; GOA-024 (Scholarship matcher) queries "ScholarshipProgram records" for its diff engine. Neither table is populated by any ingestion ticket — GOA-010/015/041 all emit `list[Document]` for similarity search only, and no `scholarship_programs` table exists at all. This ticket adds the structured extraction path: adapters dual-write a structured row **and** chunked documents, and a new `scholarship_programs` table is created and populated.

**Context — the structured-data gap:**

The opportunity-matching value proposition depends on queryable structured fields (minimum ECTS, minimum IELTS, deadlines, award amounts), but:
- GOA-015's adapters implement `SourceAdapter.scrape() → list[Document]` — unstructured chunks for `documents` only.
- GOA-012's hard gates read `program.min_ects`, `program.accepted_degrees` from `program_requirements` — a table created in GOA-006 but populated by nothing.
- GOA-024 scores "ScholarshipProgram records updated in the last 24 hours" — but `rag_db` has no scholarship table; `notifications_sent.program_id` even foreign-keys to `program_requirements`, conflating scholarships with university programs (scholarships need deadlines and award amounts that programs lack).

**Acceptance criteria:**

- New table `scholarship_programs` in `rag_db`:
  ```sql
  CREATE TABLE scholarship_programs (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  VARCHAR(255) NOT NULL,
    provider              VARCHAR(255) NOT NULL,        -- 'DAAD', 'Chevening', 'Erasmus+'
    country               VARCHAR(100),
    degree_level          VARCHAR(100),
    award_amount          VARCHAR(255),                 -- free-text (varies: monthly stipend, full tuition)
    deadline              DATE,
    eligibility           JSONB NOT NULL DEFAULT '{}',  -- structured eligibility rules
    citizenship_eligible  BOOLEAN DEFAULT TRUE,         -- open to Egyptian applicants
    min_gpa               DECIMAL(4,2),
    min_ielts             DECIMAL(3,1),
    source_url            VARCHAR(500) NOT NULL,
    content_hash          VARCHAR(64) NOT NULL,
    last_scraped_at       TIMESTAMP DEFAULT NOW(),
    updated_at            TIMESTAMP DEFAULT NOW(),
    UNIQUE (provider, name)
  );
  ```
- Migration `008_add_scholarship_programs.sql` added to the RAG service migration set
- Dual-write extraction: adapters extract structured rows **in addition to** the existing chunked `Document` output — both paths run from the same scrape (parallel to the GOA-086 pattern)
- `MastersPortalAdapter` populates `program_requirements` rows: `university, country, degree_level, min_ects, min_gpa, min_ielts, citizenship_required`
- `DAADAdapter` and `CheveningAdapter` populate `scholarship_programs` rows including `deadline` and `award_amount`
- RAG internal endpoints: `POST /internal/program-requirements` (upsert, keyed by `university + degree_level + country`) and `POST /internal/scholarship-programs` (upsert, keyed by `provider + name`) — both idempotent via `content_hash`
- `goa_ingestion_structured_rows_total` Prometheus counter with label `table (program_requirements|scholarship_programs)`
- Existing unstructured `documents` ingestion is unchanged — this adds the structured path alongside it

**Downstream ticket impacts:**

- **GOA-006**: migration list extended with `008_add_scholarship_programs.sql`
- **GOA-012** (Profile Matcher): hard gates now read real `program_requirements` rows populated here, not assumed/seed data
- **GOA-024** (Scholarship matcher): "ScholarshipProgram records" now resolve to the `scholarship_programs` table; its diff query targets `scholarship_programs.last_scraped_at`. The `notifications_sent.program_id` reference should point at `scholarship_programs.id`, not `program_requirements.id`
- **GOA-015**: its four adapters are extended here to dual-write structured rows — coordinate so GOA-088 lands in the same sprint
- **GOA-086** (visa requirements): already follows this dual-write pattern — GOA-088 generalises it to programs and scholarships

**Implementation notes:**

Structured extraction reuses each adapter's already-fetched HTML — add a `scrape_structured() → list[ProgramRequirement | ScholarshipProgram]` method alongside the existing `scrape()`. For semi-structured sources, use an LLM extraction pass (Claude Haiku, JSON mode) to pull fields the HTML doesn't expose cleanly. Idempotency via `content_hash` on the normalised row. The RAG upsert endpoints use `INSERT ... ON CONFLICT ... DO UPDATE`.

**Tests / Definition of done:**

- Unit: `MastersPortalAdapter.scrape_structured()` extracts a `program_requirements` row with correct `min_ects`/`min_ielts` from fixture HTML
- Unit: `CheveningAdapter.scrape_structured()` extracts a `scholarship_programs` row with correct `deadline` and `award_amount` from fixture HTML
- Integration: an ingestion run populates both `program_requirements` and `scholarship_programs` and writes chunked `documents` from the same sources
- Integration: `POST /internal/scholarship-programs` upserts a row; re-running the same payload is idempotent (no duplicate, `last_scraped_at` updated)
- Integration: GOA-012 hard gate reads a real `program_requirements` row and blocks a profile with insufficient ECTS
- Integration: GOA-024 diff query returns `scholarship_programs` rows with `last_scraped_at` in the last 24 hours

---

---

## Blocked By Dependency

### GOA-067 — Speaking service — holistic exam evaluation endpoint POST /evaluate/holistic(Blocked By GOA-052)

**Link:** https://trello.com/c/vfaMsCAr

| | |
|---|---|
| **Service** | Speaking |
| **Type** | AI/Agents |
| **Language(s)** | Go |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-013 (Sprint 2) — Speaking swarm — 4 IELTS evaluation agents (Fluency, Lexical, Grammar, Pronunciation) with metrics; GOA-052 (Sprint 2) — Speaking exam mode — holistic Part 1/2/3 evaluation with post-exam feedback |

**Summary:** New endpoint on the Speaking service that accepts all 3 part transcripts at once and runs the 4 agents with full context. Distinct from the single-response practice evaluation. Returns extended result with part_notes and examples per criterion.

**Acceptance criteria:**

- POST /evaluate/holistic accepts {session_id, part1: {question, transcript}, part2: {cue_card, transcript}, part3: {questions_and_answers}} — called only by Exam service after all 3 parts submitted
- Builds concatenated context string: [IELTS Speaking Exam] Part 1 (Interview): Q: {q} A: {transcript} Part 2 (Long Turn — {topic}): Cue: {cue} A: {transcript} Part 3 (Discussion): {qa_pairs}
- 4 agent goroutines run in parallel — each receives the full context and evaluates only its criterion
- Each agent returns extended schema: {criterion, band (float), overall_feedback (str), part_notes: {part1: str, part2: str, part3: str}, examples: [{part: int, quote: str, issue: str}], improvement_tip: str}
- improvement_tip is a single concrete actionable sentence per criterion — e.g. "Record yourself answering Part 2 cue cards on unfamiliar topics and listen back for filler word patterns"
- Overall band = mean of 4 criterion bands rounded to nearest 0.5
- Total evaluation time target: P95 under 8000ms (4 parallel goroutines, ~1500 token input each)
- Result written back to exam_db via Exam service internal API POST /internal/sessions/:id/result
- goa_speaking_holistic_evaluation_ms Prometheus histogram separate from practice evaluation metric

**Implementation notes:**

New Fiber route /evaluate/holistic. Context builder function assembles the prompt string from 3 part structs. Same goroutine pattern as GOA-013 but with extended response schema. Use claude-sonnet-4-6 for quality. Parse extended JSON response via Go struct with json tags.

**Implementation reference:**

```go
// Extended agent response schema
type HolisticAgentResult struct {
    Criterion      string            `json:"criterion"`
    Band           float32           `json:"band"`
    OverallFeedback string           `json:"overall_feedback"`
    PartNotes      map[string]string `json:"part_notes"`
    Examples       []TranscriptExample `json:"examples"`
    ImprovementTip string            `json:"improvement_tip"`
}

type TranscriptExample struct {
    Part  int    `json:"part"`
    Quote string `json:"quote"`
    Issue string `json:"issue"`
}
```

**Tests / Definition of done:**

- Unit: context builder correctly assembles all 3 parts with correct labels and formatting
- Unit: agent response parser correctly extracts part_notes map and examples slice
- Unit: overall band calculation rounds 6.625 to 6.5 (nearest 0.5)
- Load test: 10 concurrent holistic evaluations complete P95 under 8000ms

---

---

### GOA-068 — Writing service — exam task evaluation with extended feedback schema(Blocked By GOA-053)

**Link:** https://trello.com/c/bA7wjaNn

| | |
|---|---|
| **Service** | Writing |
| **Type** | AI/Agents |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 2 |
| **Dependencies** | GOA-014 (Sprint 2) — Writing swarm — 4 evaluation agents (Task Response, Cohesion, Vocabulary, Grammar) with metrics; GOA-053 (Sprint 2) — Writing exam mode — immediate per-task feedback with weighted combined result |

**Summary:** Extend the Writing swarm for exam-mode evaluations with richer feedback. All user input is typed text. Academic Task 1: GPT-4V reads the STIMULUS CHART (system-provided question image, not user-uploaded) to understand what it shows, then evaluates the user typed response for accuracy. General Training Task 1: text-only evaluation, no image. Task 2: standard text essay evaluation.

**Acceptance criteria:**

- POST /essays/evaluate/exam accepts {session_id, task_number (1|2), exam_type (academic|general), response_text: str, stimulus_s3_key (for Academic Task 1 chart — this is the QUESTION image, never the user essay)} — called by Exam service
- Academic Task 1 pipeline: (1) call GPT-4V with the stimulus CHART IMAGE (the exam question provided by the system) to extract what it actually shows — key data, trends, ranges. (2) pass chart extraction + user TYPED response to 4 Writing agents. GPT-4V never sees the user essay — only the question chart.
- General Training Task 1 pipeline: pass letter scenario text + bullet points + user response to 4 Writing agents — no GPT-4V step
- Task 2 pipeline: same for Academic and General — standard essay prompt + user response to 4 Writing agents
- Task Achievement agent system prompt has 3 variants: academic_task1 (check data accuracy, trends, comparisons), general_task1 (check bullet points, register, format), task2 (check argument, position, examples)
- Extended agent response schema: {criterion, band, feedback, inline_issues: [{start_char: int, end_char: int, issue_type: str, suggestion: str}], improvement_tip: str}
- inline_issues enable the frontend to highlight specific spans of the user text with colour-coded annotations per criterion
- word_count field returned in evaluation result — used by frontend for under-minimum warnings
- goa_writing_exam_evaluation_ms histogram with label: task_type (academic_task1|general_task1|task2)

**Implementation notes:**

FastAPI endpoint. Separate PromptTemplate per task type loaded from /prompts/ directory. GPT-4V call only for academic_task1. asyncio.gather for 4 agents. inline_issues generated by asking the LLM to return character-level annotations in its JSON output.

**Implementation reference:**

```python
# Task 1 prompt routing
PROMPT_TEMPLATES = {
    "academic_task1": PromptTemplate(
        template=ACADEMIC_TASK1_TEMPLATE,
        input_variables=["criterion","graph_extraction","user_response"]
    ),
    "general_task1": PromptTemplate(
        template=GENERAL_TASK1_TEMPLATE,
        input_variables=["criterion","letter_scenario","bullet_points","user_response"]
    ),
    "task2": PromptTemplate(
        template=TASK2_TEMPLATE,
        input_variables=["criterion","essay_prompt","user_response"]
    )
}
```

**Tests / Definition of done:**

- Unit: academic_task1 route calls GPT-4V before agents; general_task1 and task2 do not
- Unit: inline_issues character ranges are within the bounds of the submitted response_text length
- Integration: submit Academic Task 1 with a bar chart image — verify Task Achievement feedback references actual chart data from GPT-4V extraction
- Integration: submit General Training Task 1 letter missing one bullet point — verify Task Achievement flags the missing point

---

---

### GOA-019 — Chat UI — SSE streaming, CV upload, and speaking interface(Blocked By GOA-018)

**Members:** Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/ORVKF8oj

| | |
|---|---|
| **Service** | Frontend |
| **Type** | Frontend |
| **Language(s)** | TypeScript |
| **Priority** | P2 |
| **Story points** | 3 |
| **Dependencies** | GOA-009 (Sprint 1) — Next.js app scaffold with chat UI shell and routing; GOA-018 (Sprint 2) — Orchestration service — wire downstream service calls for all intents (Python/httpx) |

**Summary:** Add real functionality to the chat UI: streaming text responses, file upload for CVs and essays, and the audio interface for speaking practice.

**Acceptance criteria:**

- Chat messages stream token-by-token via SSE — text appears as LLM generates it
- Essay input: expandable textarea for writing practice — plain text only. CV upload (PDF only) available separately in profile page for CV review feature.
- Speaking: "Start Speaking" button requests microphone permission, streams audio via WebSocket to Speaking service, displays live transcript
- Speaking: after session ends, displays evaluation results with band scores per criterion
- Opportunity results: rendered as cards with confidence score bar, program name, university, country, deadline
- Error states: service unavailable shown as friendly message, not raw error
- Typing indicator shown while awaiting response

**Implementation notes:**

EventSource API for SSE. MediaRecorder API for audio capture, chunked via WebSocket. React state machine for speaking session: idle → listening → transcribing → evaluating → done. Tailwind for styling.

**Tests / Definition of done:**

- E2E: upload PDF, verify upload progress shown, verify extraction result displayed
- E2E: start speaking session, speak test phrase, verify transcript appears
- E2E: upload a PDF CV — verify upload progress bar reaches 100% then Processing state shown then CV filename appears
- E2E: start speaking session — verify waveform visualiser canvas animates while microphone is active

---

---

### GOA-053 — Writing exam mode — immediate per-task feedback with weighted combined result (Blocked By GOA-014)

**Members:** Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/LPidehTg

| | |
|---|---|
| **Service** | Exam |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P2 |
| **Story points** | 2 |
| **Dependencies** | GOA-014 (Sprint 2) — Writing swarm — 4 evaluation agents (Task Response, Cohesion, Vocabulary, Grammar) with metrics; GOA-048 (Sprint 1) — Exam service scaffold — FastAPI + exam_db + Academic/General split; GOA-049 (Sprint 1) — Cambridge IELTS content ingestion — Reading and Listening question banks |

**Summary:** IELTS exam mode for Writing. All responses are typed text — no image uploads. Academic Task 1: user views a chart/graph image (stimulus) and types their description. GPT-4V reads the stimulus chart to understand what it shows, providing context for evaluating whether the user described it accurately. General Training Task 1: letter scenario shown as text, user types letter. Two different Task 1 system prompts depending on exam type. Task 1 evaluated immediately on submission; Task 2 on final submit.

**Acceptance criteria:**

- GET /exam/writing/start accepts {examType: academic|general} — returns session with Task 1 prompt (image S3 pre-signed URL for Academic graph, or letter scenario text for General) and Task 2 essay prompt
- All prompts sourced from Cambridge IELTS books stored in exam_db
- PUT /exam/writing/:sessionId/submit accepts {task1_text: str, task2_text: str} — both are typed plain text, no file upload
- Task 1 and Task 2 each evaluated independently by 4-agent Writing swarm (GOA-014)
- Final Writing band = (Task1_band x 0.33) + (Task2_band x 0.67) — official IELTS weighting
- Word count warning (not hard block): under 150 words Task 1 or under 250 words Task 2
- ExamResult stored in exam_db with skillArea=writing
- Task 1 evaluation triggered IMMEDIATELY on Task 1 submission — does not wait for Task 2. User sees Task 1 results in a side panel while writing Task 2. This is correct because Tasks 1 and 2 are independent.
- Academic Task 1 evaluation: (1) GPT-4V reads the STIMULUS CHART IMAGE (not the user essay) to extract what the graph actually shows — key data, trends, ranges. (2) 4 Writing agents receive: GPT-4V chart extraction + user typed response. The chart image is never submitted by the user — it is the exam question stimulus provided by the system. User always types their response.
- General Training Task 1 evaluation pipeline: no image step. 4 Writing agents receive: letter scenario text, required bullet points list, and user response. Task Achievement agent checks: all bullet points addressed? appropriate register (formal/informal)? correct opening and closing?
- Task 2 evaluation pipeline: identical for Academic and General Training. Standard essay prompt, 4 agents evaluate. No image, no special context beyond the prompt.
- Task 1 system prompt distinguished from Task 2 by exam_type and task_number fields — two separate prompt templates stored in the Writing service
- Final Writing band = round_to_nearest_half((task1_overall_band x 0.33) + (task2_overall_band x 0.67))
- Results page layout: Task 1 result card (left) + Task 2 result card (right) + combined band prominently at top. Each card shows: task band, 4 criterion scores, inline colour-coded feedback on submitted text, word count achieved
- Word count warning displayed on results page if under minimum: 'Your Task 1 was 132 words. Responses under 150 words are penalised for Task Achievement.'
- goa_writing_exam_task1_evaluation_ms and goa_writing_exam_task2_evaluation_ms Prometheus histograms tracked separately

**Implementation notes:**

Task 2 reuses existing Writing swarm unchanged. Task 1 Academic uses GPT-4V with the stimulus image. Task 1 General uses Claude text-only with letter scenario. Academic Task 1 system prompt adjusted for graph/chart description.

**Tests / Definition of done:**

- Unit: final band calculation correctly applies 0.33/0.67 weighting
- Unit: word count validation correctly handles multiple spaces and punctuation
- Integration: Academic exam — submit Task 1 graph description + Task 2 essay, verify weighted final band in result
- Unit: Task 1 evaluation fires immediately on Task 1 submit without blocking Task 2 access
- Unit: Academic Task 1 pipeline calls GPT-4V before Writing agents; General Training Task 1 skips GPT-4V
- Unit: final band calculation correctly applies 0.33/0.67 weighting and rounds to nearest 0.5
- Integration: Academic Writing exam — submit Task 1 graph description (GPT-4V context used), verify Task Achievement feedback references actual chart data. Submit Task 2, verify weighted combined band on results page
- Unit: final band calculation rounds 6.83 to 7.0 (nearest 0.5)
- Unit: final band calculation keeps 6.5 as 6.5 (exact half round-trip)
- Integration: Academic Writing — submit Task 1 then verify Task 1 side panel shows result while Task 2 editor remains editable
- Integration: submit Task 1 with 130 words — verify under-minimum warning shown on results page with exact word count displayed

---

---

## In Progress

### GOA-074: CI/CD — branch strategy, protected branches, and GitHub OIDC AWS trust(blocked by goa-11, 70)

**Members:** Fady ehab · **Link:** https://trello.com/c/zmc5B1MY

| | |
|---|---|
| **Service** | DevOps |
| **Type** | Infrastructure |
| **Language(s)** | TypeScript |
| **Priority** | P1 |
| **Story points** | 2 |
| **Dependencies** | GOA-011 (Sprint 1) — CI pipeline — GitHub Actions with per-service test runs; GOA-070 (Sprint 1) — Terraform — RDS, RDS Proxy, ElastiCache, SQS, Secrets Manager, IAM, and observability modules |

**Summary:** Establish the team git workflow and the secure CI/CD authentication mechanism. No long-lived AWS credentials stored anywhere. Branch protection rules enforced in GitHub.

**Acceptance criteria:**

- Branch strategy documented in /docs/git-workflow.md: feature/* branches → PR against develop → merge to develop (deploys to staging) → PR from develop to main (deploys to production, requires manual approval)
- GitHub branch protection rules configured via Terraform github provider: develop and main are protected branches, require 1 PR approval, require all CI checks to pass, no force push, no deletion
- GitHub OIDC provider created in AWS IAM via Terraform (GOA-070). Two IAM roles: goa-staging-deploy (can update staging ECS services + push to staging ECR repos) and goa-production-deploy (same for production, additionally requires MFA condition on assume-role)
- GitHub Actions workflows use aws-actions/configure-aws-credentials@v4 with role-to-assume pointing to the OIDC role ARN — zero static credentials in GitHub Secrets or repository
- GitHub Secrets (non-AWS): LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, STRIPE_TEST_SECRET_KEY (for CI tests only) — these are not AWS credentials and are acceptable as GitHub Secrets
- Staging deploy triggered by push to develop branch. Production deploy triggered by push to main branch with environment: production gate requiring a named reviewer approval in GitHub.

**Implementation notes:**

Terraform github provider (hashicorp/github) manages branch protection. OIDC thumbprint fetched automatically. Separate workflow files: ci.yml (runs on all PRs), deploy-staging.yml (runs on develop push), deploy-production.yml (runs on main push with environment gate).

**Tests / Definition of done:**

- PR without review approval cannot be merged to develop (branch protection enforced)
- GitHub Actions can assume staging deploy role via OIDC without any static AWS credentials
- Attempting to push directly to main without a PR is rejected by GitHub
- Branch protection: attempt direct push to main without PR — verify push rejected by GitHub
- OIDC: GitHub Actions workflow succeeds with aws sts get-caller-identity using OIDC role — no static credentials configured

---

### GOA-049: Cambridge IELTS content ingestion — Reading and Listening question banks(blocked by goa-48)

**Members:** Fady ehab · **Link:** https://trello.com/c/Ihrc66A2

| | |
|---|---|
| **Service** | Exam |
| **Type** | Data |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 4 |
| **Dependencies** | GOA-048 (Sprint 1) — Exam service scaffold — FastAPI + exam_db + Academic/General split |

**Summary:** Parse Cambridge IELTS books 14-18 (Academic and General Training) into exam_db. Reading passages as text. Listening audio in S3. First load: 40 test records across 2 skills.

**Acceptance criteria:**

- Content parser accepts PDF input and extracts: passage text, questions, question type (MC|matching|TFNG|fill-blank|short-answer), answer key
- Academic Reading: 3 passages, 40 questions, 60 min per test stored as one record
- General Training Reading: Section 1 (social), Section 2 (work), Section 3 (general interest) — same 40Q/60min but passage types tagged
- Listening: 4 sections, 40 questions, audio file reference stored as S3 key (MP3 uploaded to S3 at exam-audio/{bookRef}/{testNumber}/section{n}.mp3)
- Minimum viable bank on first load: Cambridge IELTS 14-18 — 5 books x 4 tests x 2 skills = 40 test records
- Speaking cue cards and Writing prompts from books 14-18 also stored in question bank
- Idempotent: re-running parser on same book does not create duplicates (keyed by bookRef + testNumber + skillArea)
- GET /internal/question-bank/stats returns counts by book, skill, examType

**Implementation notes:**

Python with pdfplumber for PDF parsing. Semi-automated: parser extracts structure, human review confirms answer keys. No vector embedding needed — exam content served as-is.

**Tests / Definition of done:**

- Unit: parser correctly identifies all question types from sample Cambridge IELTS PDF page
- Integration: ingest Cambridge IELTS 18 Test 1 Academic Reading — verify 40 questions and 3 passages stored
- Integration: GET /internal/question-bank/stats returns non-zero counts after ingestion
- Integration: ingest Cambridge IELTS 18 Test 2 Academic Reading — verify passage count = 3 and question count = 40 and answer key entries = 40

---

### GOA-051 — Listening exam engine — S3 pre-signed audio delivery, auto-grading

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/L4sqP8Hf

| | |
|---|---|
| **Service** | Exam |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-049 (Sprint 1) — Cambridge IELTS content ingestion — Reading and Listening question banks; GOA-050 (Sprint 2) — Reading exam engine — static delivery, auto-grading, band score conversion |

**Summary:** Listening exam flow with zero AI. Audio delivered from S3 via pre-signed URLs, questions answered during playback, auto-graded on submission.

**Acceptance criteria:**

- GET /exam/listening/start — returns random unseen Listening test: 4 section pre-signed S3 URLs (2 hour expiry), all 40 questions, 40 minute time limit
- Pre-signed URLs expire after 2 hours — cannot be shared between users or reused across sessions
- PUT /exam/listening/:sessionId/submit — identical grading logic to Reading, uses official Listening band conversion table
- Result: raw_score, band_score, per_question_result, section_breakdown (sections 1-4)
- goa_exam_listening_sessions_total counter, goa_exam_listening_score histogram
- goa_exam_grading_latency_ms{skill_area=listening} — target P95 under 100ms

**Implementation notes:**

boto3 generate_presigned_url with 7200s expiry. Grading logic shared with Reading via common grader utility module. Pre-signed URLs generated fresh on each session start.

**Tests / Definition of done:**

- Unit: pre-signed URLs generated with correct S3 key format and 7200s expiry
- Unit: grading produces correct raw score for known answer set
- Integration: start listening session, verify 4 pre-signed URLs returned, submit, verify result
- Security: attempt to use a pre-signed URL from a different user session — verify Gateway session ownership check blocks the request with 403

---

---

### GOA-050 — Reading exam engine — static delivery, auto-grading, band score conversion

**Members:** Fady ehab · **Link:** https://trello.com/c/cRwrfOUX

| | |
|---|---|
| **Service** | Exam |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-049 (Sprint 1) — Cambridge IELTS content ingestion — Reading and Listening question banks |

**Summary:** Reading exam flow with zero AI. Deliver passages and questions, accept answers, auto-grade against answer key, convert raw score to IELTS band via official conversion tables.

**Acceptance criteria:**

- GET /exam/reading/start accepts {examType: academic|general} — returns random unseen test: all 3 passages + 40 questions, timer 3600 seconds
- Answer key NOT included in start response — server-side only until after submission
- PUT /exam/reading/:sessionId/submit accepts {answers: {q1: "TRUE", q2: "B", ...}} — grades on server immediately
- Grading: case-insensitive exact match for fill-blank, option match for MC, TRUE/FALSE/NOT GIVEN for TFNG
- Raw score 0-40 converted via official Academic or General Training band table stored in exam_db
- Result: raw_score, band_score, per_question_result (correct/incorrect + correct_answer revealed), section_breakdown (sections 1/2/3)
- goa_exam_reading_sessions_total counter (exam_type label), goa_exam_reading_score histogram
- goa_exam_grading_latency_ms histogram with label skill_area=reading — target P95 under 100ms

**Implementation notes:**

Band score conversion tables seeded as JSON on startup in exam_db. Grading is pure Python — no LLM, no external calls. Section breakdown from question_number ranges.

**Tests / Definition of done:**

- Unit: grading correctly scores fill-blank case-insensitively and trims whitespace
- Unit: band conversion returns correct band for raw scores 0, 10, 20, 30, 35, 39, 40 — Academic and General
- Unit: expired session (over 3630s elapsed) returns 403
- Integration: full Reading exam start to result with known answer key

---

---

### GOA-071 — Terraform — ECS cluster, task definitions, and service definitions for all 9 services

**Members:** Ahmed Dorgham · **Link:** https://trello.com/c/lh7lA0j0

| | |
|---|---|
| **Service** | DevOps |
| **Type** | Infrastructure |
| **Language(s)** | TypeScript |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-069 (Sprint 1) — Terraform module structure — core IaC foundation for all AWS resources; GOA-070 (Sprint 1) — Terraform — RDS, RDS Proxy, ElastiCache, SQS, Secrets Manager, IAM, and observability modules |

**Summary:** Define all 9 ECS Fargate services in Terraform. Each service gets a task definition, ECS service, and ALB target group registration. This is the Terraform equivalent of the docker-compose.yml for production.

**Acceptance criteria:**

- Module: ecs-cluster — one ECS Fargate cluster per environment. Container Insights enabled.
- Module: ecs-service — parameterised module used for each of the 9 services. Parameters: image_uri (ECR), cpu, memory, desired_count, environment_variables (from Secrets Manager valueFrom + plaintext), port, health_check_path
- Task definitions for all 9 services: Gateway (256 CPU / 512 MB), User (256/512), Orchestration (512/1024), Speaking (512/1024), Writing (512/1024), RAG (512/1024), Exam (256/512), Notification (Lambda — not ECS), Ingestion (Lambda — not ECS)
- ECS services configured with rolling deployment: minimum_healthy_percent=100, maximum_percent=200 — zero downtime deploys
- ALB listener rules: path-based routing — /api/speaking/ws → Speaking target group, /api/exam/* → Exam target group, /api/* → Gateway target group
- ECS service auto-scaling: scale out when CPU > 70% or memory > 80%, scale in when below 30% for 10 minutes. Min 1 task, max 4 tasks per service in staging; max 10 in production
- ECR repositories created per service with lifecycle policy: keep last 10 images, delete untagged images older than 1 day. Covers all 10 repos: the 7 ECS-deployed services (Gateway, User, Orchestration, Speaking, Writing, RAG, Exam) plus the 3 Lambda workers (cv-processor, scholarship-matcher, notification-sender) — Lambda container images need the same ECR lifecycle management as ECS images.

**Implementation notes:**

One ecs-service module call per service in main.tf. image_uri references ECR repo output. Secrets injected via secrets block in task definition JSON. Auto-scaling via aws_appautoscaling_target and aws_appautoscaling_policy.

**Tests / Definition of done:**

- After apply: all 9 ECS services show desired=1 running=1 in AWS console
- ALB health checks green for all services
- Auto-scaling policy visible in ECS console for each service
- After apply: all 9 ECS services show running_count equals desired_count in AWS console
- Auto-scaling: CPU spike above 70% via stress tool in ECS exec — verify second task launches within 3 minutes

---

---

### GOA-014 — Writing swarm — 4 evaluation agents (Task Response, Cohesion, Vocabulary, Grammar) with metrics

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/iwvZyjQP

| | |
|---|---|
| **Service** | Writing |
| **Type** | AI/Agents |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 4 |
| **Dependencies** | GOA-008 (Sprint 1) — Writing service scaffold — FastAPI + text submission + S3 for CVs only |

**Summary:** Implement the 4 writing evaluation agents for computer-based text input. All essays are typed text — no image processing. Each agent evaluates one IELTS Writing rubric criterion and returns a band score with detailed feedback and character-level inline_issues annotations.

**Acceptance criteria:**

- Four agent functions: evaluate_task_response(), evaluate_cohesion(), evaluate_vocabulary(), evaluate_grammar()
- All 4 run concurrently via asyncio.gather()
- Each returns: {criterion, band_score (float 0–9), feedback (str), highlighted_issues (list[{text, issue, suggestion}])}
- POST /essays/evaluate accepts {userId, essayText, submissionType, examType} — evaluates text directly, no image step
- Results stored in writing_db essays table under evaluation_result (JSONB column)
- POST /essays/:id/evaluate returns streaming SSE response — partial results as each agent completes
- Overall IELTS Writing score = mean of 4 bands, rounded to nearest 0.5
- Langfuse: swarm trace with 4 child spans — each logs criterion, band_score, tokens, latency_ms
- Prometheus histogram goa_writing_agent_band_score labelled by criterion
- Prometheus histogram goa_writing_evaluation_latency_ms — P95 target <30000ms
- Eval metric (CI): LLM-as-Judge accuracy >80% within ±0.5 band of expert on golden dataset of 5 essays
- Feedback includes 3 specific sentence-level examples per criterion
- Each essay evaluation creates a Langfuse root trace with attributes: user_id, essay_id, task_type
- Each of the 4 asyncio agent tasks creates a Langfuse child span: criterion, band_score, prompt_tokens, completion_tokens, latency_ms
- goa_writing_evaluation_latency_ms Prometheus histogram — wall-clock time including all 4 parallel agents
- goa_writing_agent_band_score Prometheus histogram with label: criterion
- goa_writing_cache_hit_rate Prometheus gauge — ratio of cached to fresh evaluations updated after each request
- Structured log per evaluation: {user_id, essay_id, bands, overall_band, latency_ms, from_cache, total_tokens, total_cost_usd}

**Implementation notes:**

Python asyncio for concurrent agent execution. Each agent uses claude-sonnet-4-6 with a criterion-specific system prompt and the essay text. Streaming SSE: yield partial results as each asyncio task completes. Store full result as JSONB for flexible querying.

**Tests / Definition of done:**

- Unit: asyncio.gather runs all 4 agents concurrently (check wall-clock vs sequential time)
- Unit: band_score always in range 0.0–9.0
- Unit: overall score correctly rounds to nearest 0.5
- Integration: submit test essay → receive 4 evaluations + overall score
- Integration: submit an essay then check Langfuse shows 1 root trace with exactly 4 child criterion spans
- Integration: submit same essay twice — second call returns from cache; goa_writing_cache_hit_rate increases

---

---

### GOA-018 — Orchestration service — wire downstream service calls for all intents (Python/httpx)

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/5nn4YL5P

| | |
|---|---|
| **Service** | Orchestration |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P2 |
| **Story points** | 3 |
| **Dependencies** | GOA-005 (Sprint 1) — Orchestration service scaffold — FastAPI + LangChain Python Supervisor Agent; GOA-006 (Sprint 1) — RAG service scaffold — FastAPI + pgvector + LangChain Python; GOA-007 (Sprint 1) — Speaking service scaffold — Go WebSocket server + ElevenLabs STT integration; GOA-008 (Sprint 1) — Writing service scaffold — FastAPI + text submission + S3 for CVs only; GOA-012 (Sprint 2) — Profile Matcher Agent — 3-stage scoring pipeline |

**Summary:** Connect the Supervisor Agent routing to real downstream service endpoints. Each intent now calls the appropriate service and returns the actual result.

**Acceptance criteria:**

- SPEAKING intent: returns WebSocket upgrade URL for Speaking service (client connects directly)
- WRITING intent: calls Writing service POST /essays with the essay text, returns essay ID + SSE stream URL
- RAG intent: calls RAG service POST /query, returns streamed answer + sources
- OPPORTUNITY_SEARCH intent: calls RAG POST /match, returns ranked program list
- CV_REVIEW intent: uploads CV to Writing service, triggers extraction, then calls RAG for CV feedback
- Each downstream call has 30s timeout with descriptive error message on failure
- Circuit breaker: after 3 consecutive failures, mark service as degraded, return friendly fallback message for 60s
- All downstream calls include X-Correlation-ID header (same as request ID)
- goa_orchestration_downstream_latency_ms histogram with label: service — records duration of each downstream httpx call
- goa_orchestration_circuit_breaker_state gauge with label: service (0=closed, 1=open) — updated on every state transition
- X-Correlation-ID propagated in every httpx request header so downstream logs can be correlated
- On circuit open: log ERROR with structured fields {service, failure_count, opened_at, correlation_id}
- On circuit close: log INFO with structured fields {service, closed_at, downtime_s}

**Implementation notes:**

Python service class per downstream service using httpx AsyncClient. Circuit breaker using pybreaker library. Correlation ID propagated through httpx headers. SSE proxying via FastAPI async generator yielding chunks from downstream response.

**Tests / Definition of done:**

- Unit: correct downstream URL called for each intent
- Unit: circuit breaker opens after 3 failures, closes after 60s
- Integration: send "evaluate my essay" message → Writing service receives request
- Unit: simulate 3 downstream failures — goa_orchestration_circuit_breaker_state{service='rag'} flips to 1
- Integration: make a downstream call then GET /metrics shows goa_orchestration_downstream_latency_ms with correct service label

---

---

## Pending Review

### YOUSSEF GET YOUR CREDENTIALS. thank you.

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/MubcvYYy

---

## Done

### GOA-001: Bootstrap monorepo and docker-compose.yml

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/oRM6LG1O

- **Service:** DevOps
- **Type:** INFRA
- **Priority:** P1
- **Points:** 3

**Summary:**
Set up the project repository and local development environment so all 5 developers can run every service with a single command.

**Acceptance Criteria:**
- Monorepo root contains /services/{gateway,user,orchestration,speaking,writing,rag,notification,ingestion} directories
- docker-compose.yml starts all 8 services plus PostgreSQL (×5 schemas), Redis (×2), and LocalStack (SQS emulator)
- Each service has a /Dockerfile with multi-stage build (dev + prod targets)
- Root Makefile has targets: make up, make down, make logs, make test
- .env.example per service with all required keys documented
- All services reachable from each other by service name inside Docker network
- README with setup instructions: clone, cp .env.example .env, make up → system running in under 5 minutes
- Prometheus client libraries added to each service Dockerfile: github.com/prometheus/client_golang (Go), prometheus-client (Python), prom-client (TypeScript)
- Langfuse SDK added to Orchestration and RAG service dependencies in Sprint 1 — not deferred to Sprint 3
- docker-compose.yml includes Grafana (port 3001) and Prometheus scrape config pointing at all /metrics endpoints
- OTEL_SERVICE_NAME and LANGFUSE_PUBLIC_KEY env vars documented in every .env.example

**Implementation Notes:**
Use docker-compose v3.8. Each service gets its own network alias. PostgreSQL runs one instance with 5 separate databases (gateway_db, user_db, orchestration_db, speaking_db, writing_db, rag_db). LocalStack emulates SQS and S3 for local dev. Add healthcheck blocks so dependent services wait correctly.

**Code Reference:**
```
# docker-compose.yml excerpt
services:
  gateway:
    build: ./services/gateway
    ports: ["8000:8000"]
    environment:
      - DATABASE_URL=postgres://...
      - REDIS_URL=redis://redis-gateway:6379
    depends_on:
      postgres: { condition: service_healthy }

  localstack:
    image: localstack/localstack
    environment:
      - SERVICES=sqs,s3
    ports: ["4566:4566"]
```

**Tests / Definition of Done:**
- docker-compose up completes without errors
- curl http://localhost:8000/health returns 200 from gateway
- All 8 service health endpoints respond within 10 seconds of startup
- docker-compose up then curl http://localhost:3001 shows Grafana login page
- curl http://localhost:8001/metrics (Gateway) returns Prometheus text format with goa_ prefixed metrics

---

### GOA-002: Shared event schema contracts package

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/g2EXssc3

- **Service:** DevOps
- **Type:** INFRA
- **Priority:** P1
- **Points:** 2
- **Depends on:** GOA-001

**Summary:**
Create a shared /packages/contracts directory with TypeScript interfaces and Python dataclasses for all SQS event schemas. This is the single source of truth for inter-service communication.

**Acceptance Criteria:**
- TypeScript package at /packages/contracts/ts with interfaces for every SQS event type
- Python package at /packages/contracts/py with Pydantic models mirroring the TS interfaces
- Events covered: UserUpdated, CVUploaded, CVProcessed, ScholarshipMatched, NotificationRequested, IngestionCompleted
- Each event has: type (string literal), version (semver), timestamp (ISO), payload (typed)
- Both packages are importable from service code with correct types
- Version field allows forward-compatible schema evolution

**Implementation Notes:**
TypeScript: plain interfaces exported from an index.ts, no runtime overhead. Python: Pydantic BaseModel classes. Store in /packages/contracts and symlink into each service's node_modules / Python path via docker-compose volume mounts.

**Code Reference:**
```
// packages/contracts/ts/events.ts
export interface BaseEvent {
  type: string;
  version: '1.0';
  timestamp: string; // ISO 8601
  correlationId: string;
}
export interface CVUploaded extends BaseEvent {
  type: 'cv.uploaded';
  payload: { userId: string; s3Key: string; fileName: string; }
}
export interface ScholarshipMatched extends BaseEvent {
  type: 'scholarship.matched';
  payload: { userId: string; programId: string; score: number; }
}
```

**Tests / Definition of Done:**
- TS compiler accepts event objects against interfaces
- Pydantic validation rejects malformed event payloads with clear error messages
- Integration: TypeScript service imports CVUploaded interface and ts-compiler rejects object missing required fields
- Integration: Python service validates ScholarshipMatched Pydantic model and raises ValidationError on missing userId

---

### GOA-089 — CV upload endpoint — file receipt, validation, and S3 storage

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/JFWHVS6E

| | |
|---|---|
| **Service** | Writing |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 2 |
| **Dependencies** | GOA-008 (Sprint 1) — Writing service scaffold; GOA-002 (Sprint 1) — Shared event schema contracts package |

**Summary:** GOA-008 deliberately handles essay **text** only. This ticket adds the CV **file** upload path the Writing service owns — the path whose file-validation behaviour used to be buried (and contradictory) in GOA-008's tests. It receives a PDF/Word CV via multipart, validates type and size, stores it in S3 under `cvs/{userId}/`, creates the `cv_reviews` row, and publishes `CVUploaded`. Writing the object to S3 is what triggers the CV Processor (GOA-087) to extract text.

**Why this is separate from GOA-008:** GOA-008 is essay text submitted as JSON — no files, no S3. CV upload is a different content type (binary file), a different store (S3), and a different validation surface (file size, MIME type, executable rejection). Keeping them in one ticket made GOA-008 read as though essays accepted `.exe` files and 10 MB uploads. They are now cleanly split.

**Acceptance criteria:**

- `POST /cv/upload` accepts `multipart/form-data`: `{userId, file}` — user-facing, routed via Gateway with JWT (Gateway forwards userId); no INTERNAL_API_KEY
- Accepted content types: `application/pdf`, `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` (.doc/.docx). All other types — including images and `.exe` — rejected with **415 Unsupported Media Type**
- Max file size **10 MB** — larger files rejected with **413 Payload Too Large** before any S3 write (check `Content-Length`, then enforce again while streaming)
- File stored in S3 at `cvs/{userId}/{uuid}.{ext}` in the `goa-writing-files` bucket (LocalStack S3 in dev). The server-generated UUID key avoids collisions and path traversal
- Creates a `cv_reviews` row: `id, user_id, s3_key, original_filename, status (processing), uploaded_at`
- Publishes `CVUploaded` event to SQS: `{type: CVUploaded, userId, s3Key, fileName}` — the domain event of record (satisfies GOA-002)
- Extraction trigger: the S3 `ObjectCreated` event on the `cvs/` prefix triggers the CV Processor (GOA-087). The `CVUploaded` SQS event is the domain signal for other consumers, **not** the extraction trigger
- Returns **202 Accepted** with `{cvId, status: "processing"}` — extraction is asynchronous

**Implementation notes:**

FastAPI `UploadFile`. Validate MIME type and size before streaming to S3 via `boto3` (LocalStack endpoint in dev). Reject early on `Content-Length`, then enforce the 10 MB cap again while streaming to defend against a lying header. The `cv_reviews` table columns are created via the Writing service's migration set. This ticket only *writes* the CV to S3 and records it; text/field extraction is GOA-087.

**Downstream ticket impacts:**

- **GOA-008**: CV upload and all S3/file handling removed from its scope — GOA-008 is now essay-text-only
- **GOA-087** (CV Processor): the extraction handler is triggered by the S3 object this ticket writes — GOA-087 now depends on GOA-089
- **GOA-077** (onboarding): Step 4 CV upload calls this endpoint. Because GOA-089 lands in Sprint 2, the Sprint 1 onboarding wizard reaches `/chat` via the Step 4 **Skip** path; the live CV upload becomes functional when GOA-089 ships
- **GOA-018** (Orchestration): the CV_REVIEW flow uploads via this endpoint

**Tests / Definition of done:**

- Unit: file > 10 MB rejected with 413 before any S3 write
- Unit: `.exe` and `image/png` rejected with 415; PDF and DOCX accepted
- Integration: `POST /cv/upload` with a PDF → object exists in S3 at `cvs/{userId}/...`, `cv_reviews` row created with `status=processing`, response is 202
- Integration: `CVUploaded` event published to SQS after a successful store
- Integration: S3 `ObjectCreated` on `cvs/` triggers the CV Processor (GOA-087) — verified by `cv_reviews.status` transitioning to `ready`

---

---

### GOA-007: Speaking service scaffold — Go WebSocket server + ElevenLabs STT integration

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/Tw5dJBsK

- **Service:** Speaking
- **Type:** BE
- **Priority:** P1
- **Points:** 4
- **Depends on:** GOA-001

**Summary:**
Build the real-time speaking service. Establishes WebSocket connections, receives audio chunks from the client, transcribes via ElevenLabs STT, and returns text. This sprint is the audio pipeline only — agent evaluation added in Sprint 2.

**Acceptance Criteria:**
- Go service with Gorilla WebSocket upgrade at GET /ws
- Each WebSocket connection spawns a dedicated goroutine for read and write
- Client sends binary audio chunks (PCM 16kHz mono); server accumulates into buffer
- Voice activity detection (VAD): silence detection after 1.5s triggers transcription
- ElevenLabs STT API call via ElevenLabs Go SDK — returns transcript text
- Server sends JSON message back: {type:"transcript", text:"...", isFinal:true}
- Connection cleanup on disconnect: goroutines stopped, buffers freed
- Max concurrent connections: 100 (configurable via MAX_CONNECTIONS env var)
- Metrics exposed at /metrics in Prometheus format: goa_speaking_active_connections (gauge), goa_speaking_transcription_ms (histogram), goa_speaking_e2e_latency_ms (histogram) — P95 \u003c3000ms hard target
- goa_speaking_goroutine_count gauge — alert if unbounded growth detected (goroutine leak indicator)
- Every session logs structured JSON on close: {session_id, duration_s, transcript_length, e2e_ms, dropped: bool}
- GET /metrics exposes Prometheus metrics in text/plain format
- goa_speaking_active_connections Prometheus gauge — incremented on WebSocket connect, decremented on disconnect
- goa_speaking_transcription_ms Prometheus histogram — recorded after every ElevenLabs STT API call
- goa_speaking_e2e_latency_ms Prometheus histogram — recorded from first audio chunk received to first TTS audio sent
- goa_speaking_goroutine_count Prometheus gauge — updated every 5 seconds via runtime.NumGoroutine()
- goa_speaking_sessions_total counter with label: outcome (completed|dropped|error)
- Structured JSON log on every session close: {session_id, user_id, duration_s, transcription_ms, goroutines_at_close, outcome}

**Implementation Notes:**
Gorilla WebSocket for connection management. Each connection: two goroutines (readPump, writePump) communicating via channels. Audio buffer as bytes.Buffer. VAD: track last non-silent chunk timestamp, trigger transcription on gap. ElevenLabs STT API called via HTTP with multipart form. Target: transcription completes in \u003c1.5s P95.

**Code Reference:**
```
// readPump goroutine
func (c *Client) readPump() {
  defer c.cleanup()
  for {
    _, msg, err := c.conn.ReadMessage()
    if err != nil { return }
    c.audioBuffer.Write(msg)
    c.lastAudioAt = time.Now()
  }
}
// VAD ticker
go func() {
  ticker := time.NewTicker(100 * time.Millisecond)
  for range ticker.C {
    if time.Since(c.lastAudioAt) \u003e 1500*time.Millisecond
       && c.audioBuffer.Len() \u003e 0 {
      c.triggerTranscription()
    }
  }
}()
```

**Tests / Definition of Done:**
- Unit: VAD correctly detects silence gaps
- Unit: audio buffer accumulates correctly
- Load test: 50 concurrent WebSocket connections sustain without goroutine leak (use pprof)
- Integration: send WAV audio → receive correct transcript
- Integration: open then close a WebSocket session — goa_speaking_sessions_total{outcome='completed'} == 1
- Integration: GET /metrics after disconnect shows goa_speaking_active_connections == 0
- Unit: VAD silence detection fires transcription after exactly 1500ms of silence, not before
- Integration: WebSocket connect then send audio chunks then silence gap then verify transcript message received within 2 seconds

---

### GOA-006: RAG service scaffold — FastAPI + pgvector + LangChain Python

**Members:** Ahmed Mounir, Youssef Mohamed · **Link:** https://trello.com/c/I5CJtfWm

| | |
|---|---|
| **Service** | RAG |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-001 (Sprint 1) — Bootstrap monorepo and docker-compose.yml; GOA-002 (Sprint 1) — Shared event schema contracts package |

**Summary:** Set up the RAG service with its vector database, basic document retrieval, and a simple Q&A endpoint. This sprint focuses on the plumbing; actual data ingestion happens in GOA-015.

**Acceptance criteria:**

- FastAPI app connected to rag_db with pgvector extension enabled
- Document model: id, content, embedding (vector 1536), source_url, category, last_updated
- ProgramRequirement model: id, university, country, degree_level, min_ects, min_gpa, min_ielts, citizenship_required
- POST /query accepts {question, userId, topK=5} — returns retrieved chunks + generated answer
- Retrieval uses cosine similarity search on pgvector
- Answer generation uses Claude claude-haiku-4-5-20251001 with retrieved context injected into prompt
- GET /health endpoint
- Langfuse tracing on every LLM answer generation call — required from sprint 1
- Prometheus histogram goa_rag_query_latency_ms
- Log retrieval similarity score per query as structured JSON field
- OpenAI text-embedding-3-small used for embedding generation (1536 dims)
- Langfuse client initialised — every answer generation LLM call traced from Sprint 1
- Each /query request creates a Langfuse trace: user_id, question_hash, top_similarity_score as attributes
- Answer generation logged as Langfuse child span: model, input_tokens, output_tokens, latency_ms, cost_usd, chunks_used
- goa_rag_query_latency_ms Prometheus histogram with label: cache_hit (true/false)
- goa_rag_retrieval_similarity_score Prometheus histogram — records top chunk similarity score per query
- goa_rag_low_confidence_total counter — incremented when top similarity < 0.6
- Structured log per query: {correlation_id, question_hash, top_similarity, chunks_retrieved, cache_hit, answer_tokens, latency_ms}
- POST /internal/visa-requirements stub endpoint registered at startup — accepts upsert payload `{country, visa_type, issuing_body, requirements, proof_of_funds, ...}`, keyed by `(country, visa_type, issuing_body)`. Implementation is a no-op returning 200 until migration 007 runs; fully implemented as part of **GOA-086** (Sprint 2)

**Implementation notes:**

FastAPI with asyncpg for async DB access. pgvector Python client for similarity search. LangChain RetrievalQA chain with ChatAnthropic. Embeddings cached: if a document chunk already has an embedding, skip re-embedding. Connection pool via asyncpg.

Migration files run in order on startup:
- `001_enable_pgvector.sql` — `CREATE EXTENSION IF NOT EXISTS vector`
- `002_create_documents.sql` — documents table with 1536-dim embedding column
- `003_create_program_requirements.sql` — program_requirements table
- `004_create_local_user_profiles.sql` — local profile snapshot table (consumed in GOA-017)
- `005_create_faq_entries.sql` — FAQ cache table with pg_trgm index
- `006_add_checklists.sql` — checklists and checklist_item_states tables (GOA-084, Sprint 3)
- `007_add_visa_requirements.sql` — visa_requirements table with proof_of_funds JSONB column (GOA-086, Sprint 2)

Migration runner executes all files in numeric order at service startup. Files for tables owned by later tickets must exist in the repo from Sprint 1 even if empty — the migration runner must not error on a file that creates a table not yet populated.

**Implementation reference:**

```python
# Vector similarity search
async def search_similar(query_embedding: list[float], top_k: int = 5):
    return await db.fetch("""
        SELECT id, content, source_url,
               1 - (embedding <=> $1::vector) AS similarity
        FROM documents
        ORDER BY embedding <=> $1::vector
        LIMIT $2
    """, query_embedding, top_k)
```

**Tests / Definition of done:**

- Unit: embedding function returns 1536-dim vector
- Unit: similarity search returns topK results ordered by cosine distance
- Integration: POST /query with a sample question returns answer + sources
- Integration: POST /query then check Langfuse shows trace with retrieval span and answer generation span
- Integration: submit low-similarity query then GET /metrics shows goa_rag_low_confidence_total incremented

---

### GOA-004: User service scaffold — NestJS with PostgreSQL and TypeORM

**Members:** Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/DhOv7p2T

- **Service:** User
- **Type:** BE
- **Priority:** P1
- **Points:** 2
- **Depends on:** GOA-001, GOA-002

**Summary:**
Bootstrap the User service with its own PostgreSQL database. Implements user registration, login verification (delegates JWT issuance to Gateway), and profile CRUD.

**Acceptance Criteria:**
- NestJS app with TypeORM connected to user_db
- User entity: id (UUID), email, passwordHash, name, subscriptionTier (free|paid), createdAt
- UserProfile entity: userId (FK), degreeLevel, gpa, ieltsScore, targetCountries[], fieldOfStudy, ects
- POST /users — register new user (validates email uniqueness, bcrypt hashes password)
- GET /users/:id — returns user + profile (internal only, no public auth)
- PUT /users/:id/profile — update profile fields
- Database migration files in /migrations, run via TypeORM CLI
- Internal service-to-service auth via shared INTERNAL_API_KEY header

**Implementation Notes:**
NestJS modular structure: UsersModule, ProfilesModule. TypeORM entities with proper indices on email and userId. Use class-validator for DTO validation. Internal endpoints protected by a simple API key guard (not JWT — services are inside the Docker network).

**Code Reference:**
```
// user entity
@entity() export class User {
  @primarygeneratedcolumn('uuid') id: string;
  @column({ unique: true }) email: string;
  @column() passwordHash: string;
  @column({ default: 'free' }) subscriptionTier: 'free' | 'paid';
  @createdatecolumn() createdAt: Date;
  @onetoone(() =\u003e UserProfile) profile: UserProfile;
}
```

**Tests / Definition of Done:**
- Unit: DTO validation rejects missing fields
- Unit: duplicate email returns 409
- Integration: full register → get profile round-trip
- Integration: PUT /users/:id/profile with invalid GPA (negative number) returns 422 with field-level error message

---

### GOA-076: Auth — password reset flow and email verification on registration(Blocked goa-4)

**Members:** Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/avrB8hA0

- **Service:** User
- **Type:** BE
- **Priority:** P1
- **Points:** 2
- **Depends on:** GOA-004, GOA-023

**Summary:**
Complete the user auth surface. Password reset via email link (time-limited token). Email verification prevents fake accounts and ensures notification emails reach real inboxes.

**Acceptance Criteria:**
- POST /auth/forgot-password accepts {email} — if email exists, generates a cryptographically random 32-byte reset token, stores hash in user_db (reset_tokens table: token_hash, userId, expiresAt=+1h, usedAt), publishes PasswordResetRequested SQS event to Notification service. Always returns 200 regardless of whether email exists (prevents user enumeration).
- POST /auth/reset-password accepts {token, newPassword} — validates token hash exists and not expired and not used, bcrypt-hashes new password, updates user record, marks token as used, revokes all refresh tokens (forces re-login on all devices).
- On registration (GOA-004): generate email verification token (32-byte random), store in user_db (email_verifications table), publish EmailVerificationRequired SQS event. User can use the app but sees a banner: "Please verify your email."
- GET /auth/verify-email/:token — marks user as verified, removes banner.
- Unverified users: can use free tier Q&A but cannot start exam sessions or receive scholarship notifications until verified.
- Notification service (GOA-023) handles: PasswordResetRequested → sends reset email with link containing raw token (not hash). EmailVerificationRequired → sends verification email.
- Rate limit on POST /auth/forgot-password: max 3 requests per email per hour (Redis, Gateway middleware) — prevents email bombing.

**Implementation Notes:**
Notification service adds two new email templates: password-reset.hbs and email-verify.hbs. Reset link: https://goa.app/reset-password?token={rawToken}. Verification link: https://goa.app/verify-email/{rawToken}.

**Tests / Definition of Done:**
- Unit: reset token expires after 1 hour
- Unit: used reset token returns 400
- Integration: request reset → check email (SES test mode) → use token → login with new password succeeds
- Security: POST /auth/forgot-password with non-existent email returns 200 (no enumeration)
```

‌

\+ Oauth

---

### GOA-069: Terraform module structure — core IaC foundation for all AWS resources

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/1LNXnodS

| | |
|---|---|
| **Service** | DevOps |
| **Type** | Infrastructure |
| **Language(s)** | TypeScript |
| **Priority** | P1 |
| **Story points** | 4 |
| **Dependencies** | GOA-001 (Sprint 1) — Bootstrap monorepo and docker-compose.yml |

**Summary:** Establish the full Terraform project structure. Every AWS resource used by GOA must be defined in Terraform — no resources created manually in the console. This ticket defines the module layout and provisions the VPC, subnets, security groups, ALB, and all networking foundations.

**Acceptance criteria:**

- Terraform project at /infra/terraform with workspaces: staging, production
- modules/ directory with one module per resource group: vpc, vpc-endpoints, ecs-cluster, rds, elasticache, sqs, secrets, iam, alb, cloudfront, lambda, eventbridge, observability
- Module: vpc — VPC with CIDR 10.0.0.0/16, 2 public subnets (ALB + NAT), 4 private subnets (ECS ×2, RDS ×2) across 2 AZs for high availability
- Module: alb — Application Load Balancer in public subnet, HTTPS listener (port 443), HTTP listener redirects to HTTPS, target groups per ECS service with health check paths
- Module: security-groups — Gateway SG (inbound 443 from ALB only), ECS services SG (inbound from Gateway SG only), RDS SG (inbound from ECS SG only), Redis SG (inbound from ECS SG only)
- Module: nat-gateway — NAT Gateway in each public subnet for outbound traffic from private subnets to external AI APIs
- Module: vpc-endpoints — Gateway Endpoint for S3 (free, no NAT cost) and Interface Endpoints for Secrets Manager and SQS — reduces NAT Gateway data transfer charges for the highest-volume internal AWS traffic
- All modules parameterised by environment (staging vs production) — different instance sizes, single-AZ vs multi-AZ
- terraform.tfvars.example per workspace documenting all required variables
- terraform plan produces zero errors on a clean AWS account
- Remote state stored in S3 bucket with DynamoDB locking table — both provisioned by a bootstrap script run once per AWS account
- Module: iam — aws_ssm_session_manager_preferences and the IAM policy attached to ECS task roles enabling ECS Exec, so developers can shell into a running container via SSM (no SSH bastion, no public RDS access, no open inbound ports)

**Implementation notes:**

Terraform ~1.7. Use aws provider ~5.0. S3 backend configured in backend.tf. Workspace-specific tfvars in /infra/terraform/environments/staging.tfvars and production.tfvars. All resource names include ${var.environment} prefix.

**Implementation reference:**

```typescript
# /infra/terraform/main.tf
terraform {
  required_version = ">= 1.7"
  backend "s3" {
    bucket         = "goa-terraform-state"
    key            = "terraform.tfstate"
    region         = "eu-west-1"
    dynamodb_table = "goa-terraform-locks"
    encrypt        = true
  }
}

module "vpc" {
  source      = "./modules/vpc"
  environment = var.environment
  cidr_block  = var.vpc_cidr
}

module "alb" {
  source            = "./modules/alb"
  environment       = var.environment
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
  certificate_arn   = module.acm.certificate_arn
}
```

**Tests / Definition of done:**

- terraform validate passes with no errors
- terraform plan against staging workspace shows correct resource count with no unexpected destroys
- After terraform apply: VPC visible in AWS console, ALB health check returns 200 on /health once Gateway is deployed
- terraform validate passes with zero errors in both staging and production workspaces
- After apply: VPC exists with correct CIDR, public and private subnets in correct AZs, IGW and NAT Gateway attached

---

---

### GOA-008: Writing service scaffold — FastAPI + text submission + S3 for CVs only

**Members:** Ahmed Dorgham · **Link:** https://trello.com/c/klEW5Yy1

- **Service:** Writing
- **Type:** BE
- **Priority:** P2
- **Points:** 2
- **Depends on:** GOA-001, GOA-002

**Summary:**
Bootstrap the Writing service. Accepts essay text submissions directly — no image upload for writing. S3 is used only for CV files and Academic Task 1 stimulus chart images. Evaluation agents added in Sprint 2.

**Acceptance Criteria:**
- FastAPI app with POST /essays/upload accepting multipart/form-data
- Supported input: plain text submission via POST body. S3 used only for CV file storage and exam Task 1 stimulus images — NOT for essay text.
- Essay text stored directly in writing_db (extracted_text column) — no S3 upload for essay content
- Essay text accepted as plain text in request body — no image extraction step
- Essay record stored in writing_db: id, userId, s3Key, extractedText, uploadedAt, status (pending|evaluated)
- GET /essays/:id returns essay metadata + extracted text
- Max essay text length: 5000 characters enforced at Gateway middleware
- S3 only used for CV storage and Academic Task 1 chart images — not for essay text

**Implementation Notes:**
FastAPI endpoint accepts {userId, essayText, submissionType, examSessionId (optional)}. Essay text stored directly in essays.extracted_text column — no S3, no OCR, no image processing. S3 only touched for CV uploads (cv_reviews table) and exam Task 1 stimulus chart images.

**Tests / Definition of Done:**
- Unit: file size validation rejects \u003e10MB uploads
- Unit: correct S3 key format generated
- Integration: POST essay text → verify stored in writing_db with status=ready immediately (no extraction delay)
- Integration: upload unsupported file type (.exe) returns 415 Unsupported Media Type

---

### GOA-003: Gateway service scaffold — Go/Fiber with JWT auth middleware

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/FHtxfMN4

- **Service:** Gateway
- **Type:** BE
- **Priority:** P1
- **Points:** 3
- **Depends on:** GOA-001

**Summary:**
Build the foundation of the Gateway service: HTTP server, JWT validation, rate limiting via Redis, and health endpoint. This is the entry point for all client requests.

**Acceptance Criteria:**
- Go module initialised with Fiber v2 framework
- POST /auth/login accepts {email, password}, returns signed JWT (HS256, 1h expiry)
- POST /auth/refresh accepts refresh token, returns new access token
- All protected routes validate JWT in Authorization: Bearer header
- Rate limiter: 60 req/min per user (Redis sliding window), returns 429 with Retry-After header
- GET /health returns {status: "ok", version, uptime} — no auth required
- Structured JSON logging via zerolog with request ID on every log line
- Graceful shutdown on SIGTERM with 10s drain window
- GET /metrics exposes Prometheus metrics in text/plain format
- goa_gateway_requests_total counter with labels: route, method, status_code
- goa_gateway_latency_seconds histogram with labels: route — buckets at 50ms, 100ms, 200ms, 500ms, 1s, 5s
- goa_gateway_rate_limit_hits_total counter with label: user_id
- goa_gateway_auth_failures_total counter — alert threshold: >50/min
- Every request log line: {request_id, user_id, route, status, latency_ms, upstream_service} structured JSON via zerolog
- X-Correlation-ID header generated on every request if absent, propagated to all downstream calls

**Implementation Notes:**
Use Fiber v2 for routing. Implement JWT middleware as a Fiber middleware function. Rate limiter uses go-redis INCR + EXPIRE pattern in a sliding window. zerolog for structured logging. Configuration via envconfig struct tags.

**Code Reference:**
```
// services/gateway/main.go
app := fiber.New(fiber.Config{
  ErrorHandler: errorHandler,
  ReadTimeout:  5 * time.Second,
  WriteTimeout: 10 * time.Second,
})
app.Use(requestIDMiddleware())
app.Use(loggingMiddleware())
app.Get("/health", healthHandler)

api := app.Group("/api", jwtMiddleware(cfg.JWTSecret))
api.Use(rateLimiterMiddleware(redisClient, 60))
```

**Tests / Definition of Done:**
- Unit: JWT middleware rejects expired/invalid tokens
- Unit: rate limiter blocks after 60 requests
- Integration: POST /auth/login returns valid JWT
- Integration: protected route with no token returns 401
- Unit: metrics registry has all 4 counters and histograms registered at startup
- Integration: make 3 requests then GET /metrics — goa_gateway_requests_total shows count 3

---

### GOA-075: Auth — refresh token rotation, logout, and token invalidation(blocked by goa-03)

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/CaIWFOOo

| | |
|---|---|
| **Service** | Gateway |
| **Type** | Backend |
| **Language(s)** | Go |
| **Priority** | P1 |
| **Story points** | 2 |
| **Dependencies** | GOA-003 (Sprint 1) — Gateway service scaffold — Go/Fiber with JWT auth middleware |

**Summary:** Complete the authentication system. Access tokens expire in 1 hour — refresh tokens allow silent re-authentication without requiring the user to log in again. Logout invalidates both tokens.

**Acceptance criteria:**

- POST /auth/refresh accepts the refresh token from httpOnly cookie, validates it against the refresh_tokens table in user_db (keyed by token hash, userId, expiresAt, revokedAt), returns a new access JWT (1h) and rotates the refresh token (new refresh token issued, old one revoked)
- Refresh tokens expire after 30 days of inactivity. Each rotation resets the 30-day window.
- POST /auth/logout: revokes the current refresh token (sets revokedAt), clears both httpOnly cookies. Returns 200.
- POST /auth/logout-all: revokes all refresh tokens for this user (all devices) — for "sign out everywhere" security feature
- If a refresh token is used after being revoked (replay attack): immediately revoke ALL refresh tokens for that user and return 401 — this forces re-login on all devices
- Access token validation via JWT signature check only — no DB lookup on every request (stateless). Refresh token validation always hits the DB.
- Redis cache for revoked access tokens: on logout, the access token jti (JWT ID) is stored in Redis with TTL = token remaining lifetime. Gateway checks this blacklist on every request to catch tokens used after logout before they expire naturally.

**Implementation notes:**

refresh_tokens table in user_db: id, user_id, token_hash (bcrypt), expires_at, revoked_at, created_at, device_hint. Gateway stores and validates refresh tokens. Access token blacklist in Redis: SET jti:${jti} 1 EX ${remaining_ttl}.

**Tests / Definition of done:**

- Unit: expired refresh token returns 401
- Unit: revoked refresh token triggers full session revocation and returns 401
- Integration: login → wait → use refresh token → new access token issued → old refresh token rejected
- Security: use refresh token twice (replay) → both sessions invalidated

---

---

### GOA-010: Ingestion worker scaffold — scraper framework + chunking pipeline(blocked by goa-06)

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/GIUYpXsq

| | |
|---|---|
| **Service** | Ingestion |
| **Type** | Data |
| **Language(s)** | Python |
| **Priority** | P2 |
| **Story points** | 2 |
| **Dependencies** | GOA-006 (Sprint 1) — RAG service scaffold — FastAPI + pgvector + LangChain Python |

**Summary:** Build the skeleton of the data ingestion pipeline. Implements a configurable scraper with pluggable source adapters and the text chunking + embedding pipeline. No real data sources yet — uses a test fixture.

**Acceptance criteria:**

- Python Lambda-compatible handler in /services/ingestion/handler.py
- SourceAdapter abstract base class with scrape(url) → list[Document] interface
- TestFixtureAdapter returns 10 hardcoded sample documents for local dev
- Chunking: RecursiveCharacterTextSplitter, chunk_size=500, overlap=50
- Embedding: text-embedding-3-small via OpenAI SDK
- Upsert to RAG service pgvector DB via RAG service internal API (not direct DB access)
- Idempotent: documents identified by hash(source_url + content[:100]) — skip if already exists
- DryRun mode: logs what would be upserted without writing (for testing)

**Implementation notes:**

Python with LangChain document loaders for chunking. Abstract SourceAdapter pattern so new sources are added by implementing one class. Embedding calls batched in groups of 100 to avoid API rate limits. Upsert via POST /internal/documents on RAG service.

**Tests / Definition of done:**

- Unit: chunker produces ≤500 token chunks with correct overlap
- Unit: duplicate detection skips already-ingested documents
- Integration (dry-run): fixture adapter processes 10 docs, logs 10 would-upsert messages
- Integration: ingest same document twice — verify second run skips embedding API call (idempotency check via mock counter)

---

### GOA-005: Orchestration service scaffold — FastAPI + LangChain Python Supervisor Agent(blocked by goa-003)

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/m6dTeGqQ

| | |
|---|---|
| **Service** | Orchestration |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-001 (Sprint 1) — Bootstrap monorepo and docker-compose.yml; GOA-002 (Sprint 1) — Shared event schema contracts package; GOA-003 (Sprint 1) — Gateway service scaffold — Go/Fiber with JWT auth middleware |

**Summary:** Build the Supervisor Agent that receives all user chat messages, maintains conversation memory, and routes to the correct downstream service (Speaking, Writing, or RAG).

**Acceptance criteria:**

- FastAPI app with Redis (orch_redis) for session memory via langchain-redis; orchestration_db (PostgreSQL) provisioned for long-term user facts added in GOA-038
- POST /chat accepts {userId, sessionId, message, attachments[]} — returns SSE streamed response via FastAPI StreamingResponse
- Supervisor Agent classifies intent into: SPEAKING | WRITING | RAG | OPPORTUNITY_SEARCH | CV_REVIEW
- LangChain ConversationBufferWindowMemory (last 10 turns) stored in Redis keyed by sessionId
- Routing logic: calls downstream service REST endpoint based on classified intent
- Supervisor returns error gracefully if downstream service is unavailable (circuit breaker pattern)
- GET /sessions/:sessionId/history — returns conversation history
- Langfuse integration: every LLM call traced with model, tokens, latency, cost — from day one, not retrofitted
- Prometheus counter goa_orchestration_intent_classified_total labelled by intent
- Prometheus histogram goa_orchestration_classification_latency_ms — P95 target <500ms
- X-Correlation-ID header propagated to all downstream calls
- Streaming via FastAPI async generator + EventSourceResponse — tokens forwarded as they arrive from Anthropic streaming API
- Langfuse client initialised at app startup — traces every LLM call from day one, not Sprint 3
- Each /chat request creates a root Langfuse trace with attributes: user_id, session_id, correlation_id
- Intent classification LLM call logged as Langfuse child span: model, input_tokens, output_tokens, latency_ms, cost_usd, classified_intent
- goa_orchestration_intent_classified_total Prometheus counter with label: intent
- goa_orchestration_classification_latency_ms Prometheus histogram — P95 target <500ms
- goa_orchestration_downstream_latency_ms Prometheus histogram with label: service
- Structured JSON log on every request completion: {correlation_id, intent, downstream_service, total_ms, status}

**Implementation notes:**

LangChain Python ChatAnthropic with a routing system prompt. Intent classification uses structured output (Pydantic model) returning an intent enum. Memory stored in Redis with TTL of 24 hours via langchain-redis. Downstream calls use httpx async client with 30s timeout. SSE streaming via FastAPI StreamingResponse and async generators.

**Implementation reference:**

```python
# Supervisor routing (LangChain Python)
from langchain_anthropic import ChatAnthropic
from langchain_redis import RedisChatMessageHistory
from pydantic import BaseModel

class IntentResult(BaseModel):
    intent: Literal["SPEAKING","WRITING","RAG","CV_REVIEW"]
    confidence: float

llm = ChatAnthropic(model="claude-haiku-4-5-20251001")
structured_llm = llm.with_structured_output(IntentResult)

SUPERVISOR_PROMPT = """You are a routing agent.
Classify the user message into exactly one of:
SPEAKING  - IELTS speaking practice or mock interview
WRITING   - essay submission or writing evaluation
RAG       - IELTS info, requirements, visa, scholarships
CV_REVIEW - CV upload or improvement request"""
```

**Tests / Definition of done:**

- Unit: intent classifier correctly routes "evaluate my essay" to WRITING
- Unit: intent classifier routes "find scholarships in Germany" to OPPORTUNITY_SEARCH
- Integration: full chat round-trip with memory — second message references first
- Integration: send one chat message then check Langfuse dashboard shows trace with correct intent span and token count
- Integration: GET /metrics shows goa_orchestration_intent_classified_total incremented with correct label
- Unit: Supervisor prompt correctly maps SPEAKING intent to Speaking service downstream URL
- Unit: Supervisor prompt correctly maps WRITING intent to Writing service downstream URL
- Integration: POST /chat with message about IELTS speaking returns SSE stream with intent=SPEAKING in first event
- Integration: Langfuse trace created for every /chat request — verified via Langfuse API after test

---

### GOA-011: CI pipeline — GitHub Actions with per-service test runs

**Members:** Fady ehab · **Link:** https://trello.com/c/SYuyAURB

- **Service:** DevOps
- **Type:** TEST
- **Priority:** P1
- **Points:** 2
- **Depends on:** GOA-001

**Summary:**
Set up GitHub Actions so every pull request runs tests for affected services automatically. Blocks merge on test failure.

**Acceptance Criteria:**
- Workflow file at .github/workflows/ci.yml
- Detects which services changed using paths filter
- For each changed service: installs deps, runs linter, runs unit tests
- Go services: golangci-lint + go test ./...
- TypeScript services: eslint + jest --coverage (fail if coverage \u003c70%)
- Python services: ruff + pytest --cov (fail if coverage \u003c70%)
- Test results reported as PR check with pass/fail per service
- Total CI time target: under 4 minutes for a single-service change

**Implementation Notes:**
GitHub Actions matrix strategy. Use actions/cache for node_modules, Go module cache, and pip cache. Parallel jobs per service. Coverage reports uploaded as artifacts.

**Tests / Definition of Done:**
- CI runs and fails correctly when a unit test is broken
- CI passes on green code
- Coverage threshold enforcement works
- CI verification: push broken TypeScript to a PR branch — verify CI fails the TypeScript check and blocks the PR

---

### GOA-009: Next.js app scaffold with chat UI shell and routing(Blocked by goa-3)

**Members:** Ahmed Dorgham, Ahmed Mounir · **Link:** https://trello.com/c/2SNXG0In

- **Service:** Frontend
- **Type:** FE
- **Priority:** P2
- **Points:** 3
- **Depends on:** GOA-003

**Summary:**
Bootstrap the Next.js frontend with basic page routing, the chat interface shell, and connection to the Gateway API. No AI features yet — just the UI skeleton.

**Acceptance Criteria:**
- Next.js 14 app with App Router in /services/frontend
- Pages: / (landing), /chat (main interface), /login, /register, /profile
- Chat UI: message list, input box, send button — no functionality yet
- Auth: JWT stored in httpOnly cookie, refresh handled transparently
- API client: axios instance pointing to Gateway at NEXT_PUBLIC_API_URL
- Tailwind CSS configured with custom design tokens matching the system palette
- Mobile-responsive layout (chat UI usable on 375px width)
- Loading skeletons on all async data fetch points

**Implementation Notes:**
Next.js 14 App Router. Server components for auth-gated pages. Client components for chat interface (needs real-time state). JWT stored in httpOnly cookie set by Gateway. API client in /lib/api.ts. Tailwind for styling.

**Tests / Definition of Done:**
- E2E (Playwright): unauthenticated user redirected from /chat to /login
- E2E: login form submits and cookie is set
- Visual: chat UI renders correctly on mobile viewport
- E2E: authenticated user at /login is redirected to /chat without showing the login form

---

### GOA-013 — Speaking swarm — 4 IELTS evaluation agents (Fluency, Lexical, Grammar, Pronunciation) with metrics

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/H4ZVunZT

| | |
|---|---|
| **Service** | Speaking |
| **Type** | AI/Agents |
| **Language(s)** | Go |
| **Priority** | P1 |
| **Story points** | 5 |
| **Dependencies** | GOA-007 (Sprint 1) — Speaking service scaffold — Go WebSocket server + ElevenLabs STT integration |

**Summary:** After transcription, run 4 parallel evaluation agents each scoring one IELTS rubric dimension. Aggregate results and stream feedback back to client.

**Acceptance criteria:**

- Four agent functions: evaluateFluency(), evaluateLexical(), evaluateGrammar(), evaluatePronunciation()
- Each agent takes transcript + question_prompt → returns {band: float, feedback: string, examples: []string}
- All 4 agents run concurrently via Go goroutines with sync.WaitGroup
- Total LLM time budget: 3 seconds P95 (all 4 run in parallel, not sequence)
- Aggregate result: {overall_band: float, dimensions: {...}, overall_feedback: string}
- Result streamed back to client via WebSocket as JSON: {type:"evaluation", ...result}
- TTS: overall_feedback text sent to ElevenLabs, audio streamed back chunk-by-chunk
- Session stored in speaking_db: sessionId, userId, transcript, evaluation, bandScores, createdAt
- Langfuse: swarm trace with 4 child spans (one per agent) — each logs criterion, band_score, tokens, latency_ms
- Prometheus histogram goa_speaking_agent_band_score labelled by criterion — track distribution over time
- Eval metric (CI): LLM-as-Judge accuracy >80% within ±0.5 band of expert on golden dataset of 20 transcripts
- Each speaking session creates a Langfuse root trace with attributes: user_id, session_id, question_type
- Each of the 4 agent goroutines creates a Langfuse child span: criterion, band_score, prompt_tokens, completion_tokens, latency_ms
- goa_speaking_agent_band_score Prometheus histogram with label: criterion — track scoring distribution over time
- goa_speaking_llm_first_token_ms histogram — time from agent goroutine start to first streaming token received
- goa_speaking_tts_first_audio_ms histogram — time from ElevenLabs request sent to first audio chunk received
- goa_speaking_e2e_latency_ms updated per session: from first audio chunk received to first TTS audio returned to client
- If goa_speaking_e2e_latency_ms > 3000ms: log ERROR with fields {session_id, transcription_ms, llm_ms, tts_ms}

**Implementation notes:**

Go goroutines for parallel agent execution. Each agent makes an independent Anthropic API call with a rubric-specific system prompt. Results collected into a channel. TTS streaming: ElevenLabs streaming API, forward audio chunks directly over WebSocket as binary messages. Use claude-sonnet-4-6 for evaluation quality.

**Implementation reference:**

```go
// Parallel agent execution
var wg sync.WaitGroup
results := make(chan AgentResult, 4)
agents := []AgentFn{evaluateFluency, evaluateLexical,
                     evaluateGrammar, evaluatePronunciation}
for _, agent := range agents {
  wg.Add(1)
  go func(fn AgentFn) {
    defer wg.Done()
    results <- fn(ctx, transcript, question)
  }(agent)
}
wg.Wait(); close(results)
```

**Tests / Definition of done:**

- Unit: all 4 goroutines complete and results merged correctly
- Unit: individual agent prompts produce valid band scores 0–9
- Load test: 20 concurrent sessions, P95 evaluation time < 3s
- Integration: full audio → transcript → evaluation → TTS round-trip
- Integration: complete a speaking session then check Langfuse shows 1 root trace with exactly 4 child agent spans
- Load test: 20 concurrent sessions — check goa_speaking_e2e_latency_ms P95 via /metrics

---

---

### GOA-090 — Gateway auth refactor — remove shared user_db access, delegate to User service internal API

**Members:** Ahmed Mounir, Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/s3Vm14V2

| | |
|---|---|
| **Service** | Gateway |
| **Type** | Backend |
| **Language(s)** | Go, TypeScript |
| **Priority** | P2 |
| **Story points** | 3 |
| **Dependencies** | GOA-075 (Sprint 1) — Auth — refresh token rotation, logout, and token invalidation; GOA-004 (Sprint 1) — User service scaffold — NestJS with PostgreSQL and TypeORM |

**Summary:** GOA-075 implemented refresh token rotation and logout by having the Go Gateway connect directly to `user_db`. This violates the database-per-service boundary: schema changes in the User service can silently break the Gateway, and connection spikes on one service starve the other. This ticket removes the Gateway's direct Postgres connection and replaces it with internal HTTP calls to new endpoints on the User service, restoring strict service isolation.

**Why this is separate from GOA-075:** GOA-075 was scoped to Sprint 1 velocity — the shared-DB approach was explicitly accepted as technical debt to avoid blocking the Gateway developer on the User service developer finishing internal endpoints. This ticket retires that debt once both services are stable.

**Acceptance criteria:**

- Gateway has zero direct Postgres connections. `DATABASE_URL` removed from gateway env vars and `docker-compose.yml` gateway service block. `github.com/lib/pq` and `golang.org/x/crypto/bcrypt` removed from `go.mod` if no longer used elsewhere.
- User service exposes three new internal endpoints (protected by `INTERNAL_API_KEY` header, not JWT):
  - `POST /internal/auth/login` — accepts `{email, password, deviceHint}`, validates credentials AND creates the refresh token record in one atomic call; returns `{userId, email, tokenId, rawToken, expiresAt}` or 401. One round-trip — no failure window between validating credentials and creating the token
  - `POST /internal/auth/refresh-tokens` — accepts `{tokenId, rawToken, deviceHint}`, returns `{userId, newTokenId, newRawToken, expiresAt}` or 401/403 (403 = replay attack detected, all sessions revoked)
  - `POST /internal/auth/revoke-tokens` — accepts `{userId, tokenId?, revokeAll: boolean}` — revokes one token or all tokens for the user; returns 200
- Gateway login handler calls `POST /internal/auth/login` instead of querying the `users` table directly. On success it receives the refresh token from the User service, issues the access JWT (with `jti`) itself, and sets both httpOnly cookies. **Design note**: access-JWT signing stays in the Gateway (it owns JWT issuance); credential validation and all refresh-token persistence move to the User service.
- Gateway refresh handler calls `POST /internal/auth/refresh-tokens`. A 403 response means replay attack — Gateway clears cookies and returns 401 to the client.
- Gateway logout/logout-all handlers call `POST /internal/auth/revoke-tokens`. Redis blacklist write (`SET jti:<jti> 1 EX <ttl>`) stays in the Gateway — Redis is an acceptable shared caching layer.
- All existing GOA-075 acceptance criteria continue to pass: rotation, 30-day window reset, replay detection, Redis blacklist.
- Internal calls use `httpx`-equivalent Go HTTP client with 5s timeout and structured error logging on failure.

**Implementation notes:**

GOA-075 implemented the `refresh_tokens` repository in the **Gateway** (`services/gateway/auth/repository.go`, Go). This ticket **ports** that logic to the User service — NestJS/TypeScript: RefreshToken entity, repository, bcrypt hashing, rotation, and replay detection — and exposes it behind `INTERNAL_API_KEY`. The port from Go to TypeScript is the bulk of the work; this is not just wrapping existing code in HTTP endpoints, which is why the ticket is 3 points. The Gateway repository file is then deleted — replaced by an HTTP client wrapper. JWT generation (`tokens.go`) and Redis blacklist logic (`jwt.go`) are unchanged.

Sequence as two PRs: (1) User service internal endpoints — the TS port, independently testable; (2) Gateway swap — delete `repository.go`, add the HTTP client wrapper. The Gateway keeps working on the old path until PR 2 lands; run the replay-attack integration test against both.

**Tests / Definition of done:**

- Unit: Gateway login handler calls User service internal login endpoint (mock HTTP); no SQL in gateway test
- Unit: replay attack — Gateway refresh handler receives 403 from User service, returns 401 and clears cookies
- Integration: full login → refresh → logout round-trip with both services running; all GOA-075 manual verification steps still pass
- Security: confirm via `docker inspect` or env dump that Gateway container has no `DATABASE_URL` set

---

---

### GOA-070: Terraform — RDS, ElastiCache, SQS, Secrets Manager, IAM modules(blocked by goa-069)

**Members:** Youssef Mohamed · **Link:** https://trello.com/c/JpaCe05a

| | |
|---|---|
| **Service** | DevOps |
| **Type** | Infrastructure |
| **Language(s)** | TypeScript |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-069 (Sprint 1) — Terraform module structure — core IaC foundation for all AWS resources |

**Summary:** Provision all stateful AWS resources in Terraform. Each service gets its own RDS database or schema, fronted by RDS Proxy to handle connection pooling across 7 ECS services and 3 Lambda functions. SQS queues with DLQs. ElastiCache Redis. Secrets Manager for all API keys. IAM roles with least-privilege policies for ECS tasks. CloudWatch Log Groups, alarms, and the SNS alert topic are also provisioned here — this is the ticket that turns the alarm specifications in GOA-027 into actual deployed infrastructure.

**Acceptance criteria:**

- Module: rds — one PostgreSQL RDS instance (db.t3.micro staging, db.t3.small production) with one database per service: user_db, orchestration_db, speaking_db, writing_db, rag_db, exam_db, notification_db, ingestion_db (8 databases). orchestration_db holds long-term conversation facts (GOA-038); short-term session memory lives in Redis. Gateway has no PostgreSQL database — it uses Redis only. Multi-AZ enabled in production only. Automated backups: 7 days.
- Module: rds-proxy — aws_db_proxy in front of the RDS instance. Required because 7 ECS services (scaling to 10 tasks each in production) plus 3 Lambda functions all open connections — Lambda cold starts in particular create new connections frequently and can exhaust max_connections without pooling.
- Module: elasticache — Redis cluster (cache.t3.micro staging, cache.t3.small production) in private subnet. Two logical databases: db=0 for Gateway rate limits, db=1 for Orchestration session memory
- Module: sqs — queues: user-events, notification-queue, ingestion-queue. Each queue has a corresponding DLQ with maxReceiveCount=3. visibility_timeout_seconds=30 on all queues
- Module: secrets — one Secrets Manager secret per service storing: ANTHROPIC_API_KEY, OPENAI_API_KEY, ELEVENLABS_API_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, DATABASE_URL per service, INTERNAL_API_KEY
- Module: iam — one ECS task execution role and one ECS task role per service. Task role has only the permissions that service needs: Gateway reads no secrets except JWT_SECRET, RAG reads ANTHROPIC_API_KEY and DATABASE_URL only. No wildcard permissions.
- Module: iam — GitHub Actions OIDC provider and role: allows github.com/org/goa-repo to assume a deploy role scoped to ECS UpdateService + ECR PutImage + ECS RegisterTaskDefinition only. No long-lived AWS access keys stored in GitHub Secrets.
- All secrets referenced in ECS task definitions via valueFrom (ARN) — never passed as plaintext environment variables
- Module: observability — aws_cloudwatch_log_group per service (30-day retention), aws_sns_topic goa-alerts with email subscription for the team, aws_cloudwatch_metric_alarm resources matching every alarm defined in GOA-027 (Speaking P95 latency, error rate per service, DLQ depth, ECS running task count) all wired to publish to the goa-alerts SNS topic — this is the actual IaC backing GOA-027 specifications, not just the alarm logic description

**Implementation notes:**

RDS password generated via random_password Terraform resource and stored in Secrets Manager. OIDC thumbprint fetched via tls_certificate data source. IAM policies written as JSON in Terraform locals.

**Tests / Definition of done:**

- After apply: all 8 RDS databases accessible from ECS subnet (test via terraform output connection strings)
- SQS queues visible with correct DLQ associations in AWS console
- GitHub Actions workflow can assume the deploy role via OIDC — no static credentials in repo
- After apply: all 8 RDS databases reachable from ECS private subnet via psql test container
- Security: verify no RDS instance has publicly_accessible = true in terraform state file

---

### GOA-077: Landing page, onboarding wizard, login, and password reset pages(blocked by goa-9, 75, 76)

**Members:** Ahmed Dorgham, Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/q02zyGIS

| | |
|---|---|
| **Service** | Frontend |
| **Type** | Frontend |
| **Language(s)** | TypeScript |
| **Priority** | P1 |
| **Story points** | 3 |
| **Dependencies** | GOA-009 (Sprint 1) — Next.js app scaffold with chat UI shell and routing; GOA-075 (Sprint 1) — Auth — refresh token rotation, logout, and token invalidation; GOA-076 (Sprint 1) — Auth — password reset flow and email verification on registration |

**Summary:** Build the frontend pages that are prerequisites for any user reaching the main application. Without these, a new user has no way to create an account and begin the onboarding journey described in the user workflow.

**Acceptance criteria:**

- Route / — landing page: hero section (headline, subheadline, CTA button), feature cards (3 columns: Opportunity Matching, IELTS Preparation, CV Review), how-it-works section (4 steps with icons), free vs paid tier comparison table, footer with links. Fully static — no API calls. SEO: meta title, description, og:image.
- Route /login — email + password form. On submit: POST /api/auth/login. On success: redirect to /chat. Show forgot password link. Error states: invalid credentials, account not verified (show resend verification link).
- Route /forgot-password — email input form. POST /api/auth/forgot-password. Show success message regardless of whether email exists.
- Route /reset-password?token=... — new password + confirm password form. POST /api/auth/reset-password. On success: redirect to /login with success banner.
- Route /verify-email/:token — calls GET /api/auth/verify-email/:token on mount. Shows success or error state. Redirects to /chat after 3 seconds on success.
- Route /onboarding — 4-step wizard (academic background → language scores → targets → CV upload). Progress bar at top. Each step validates before proceeding. Step 4 CV upload: drag-and-drop zone, shows upload progress, shows "Processing..." state while Lambda extracts. Skip button on Step 4. On completion: redirect to /chat.
- All auth pages: redirect to /chat if user is already authenticated.

**Implementation notes:**

Next.js App Router server and client components. Landing page is a server component (SEO). Auth forms are client components. Onboarding wizard state managed in sessionStorage across steps (in case of accidental navigation). react-dropzone for CV upload. The Step 4 CV upload posts to the Writing service CV endpoint (GOA-089, Sprint 2); until that lands, the Sprint 1 wizard completes via the Step 4 Skip button.

**Tests / Definition of done:**

- E2E: full registration → onboarding wizard → CV upload → /chat reached
- E2E: forgot password → email received → reset password → login with new password
- E2E: unauthenticated user at /chat redirected to /login
- SEO: lighthouse accessibility score > 90 on landing page

---

### GOA-048: Exam service scaffold — FastAPI + exam_db + Academic/General split

**Members:** Fady ehab · **Link:** https://trello.com/c/i2AgFmMf

- **Service:** Exam
- **Type:** BE
- **Priority:** P1
- **Points:** 3
- **Depends on:** GOA-001, GOA-002

**Summary:**
New microservice owning all exam session state, question banks, and scoring records. Reading and Listening served statically — no LLM involved.

**Acceptance Criteria:**
- FastAPI app with its own exam_db PostgreSQL schema (separate from all other services)
- ExamSession model: id, userId, examType (academic|general), skillArea (reading|listening|speaking|writing), status (pending|in_progress|submitted|scored), startedAt, submittedAt, timeLimitSeconds
- Question model: id, bookRef (e.g. Cambridge IELTS 18), testNumber (1-4), skillArea, examType, passageText (reading), audioS3Key (listening), questions JSON, answerKey JSON
- ExamResult model: id, sessionId, userId, skillArea, rawScore, bandScore, sectionScores JSON, gradedAt
- POST /sessions — create exam session, returns session_id and first question set (answer key never included)
- GET /sessions/:id — returns session state and remaining time in seconds
- PUT /sessions/:id/submit — submit answers, triggers immediate scoring for Reading and Listening
- GET /sessions/:id/result — full result with answer key revealed only after submission
- GET /questions/random — random unseen test for this user filtered by examType and skillArea
- Internal service auth via INTERNAL_API_KEY header
- goa_exam_sessions_total Prometheus counter with labels: skill_area, exam_type, outcome

**Implementation Notes:**
FastAPI with asyncpg. Answer key stored separately in DB, never sent to client until post-submission. Random selection uses NOT IN (previously seen test IDs for this user) to avoid repetition. Server enforces timing — client cannot manipulate.

**Code Reference:**
```
# Exam session time enforcement
async def submit_session(session_id: str, answers: dict):
    session = await db.get_session(session_id)
    elapsed = (datetime.utcnow() - session.started_at).seconds
    if elapsed > session.time_limit_seconds + 30:
        raise HTTPException(403, "Session time expired")
    return await grade_and_store(session, answers)
```

**Tests / Definition of Done:**
- Unit: session timer correctly expires session after timeLimitSeconds + 30s grace period
- Unit: answer key field not present in GET /sessions/:id response before submission
- Integration: full create, submit, result round-trip for a Reading session
- Integration: GET /metrics shows goa_exam_sessions_total after session completion

---

### GOA-054 — Exam prep UI — exam type selection, skill cards, and exam shell

**Members:** Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/5ZWPRKRS

| | |
|---|---|
| **Service** | Frontend |
| **Type** | Frontend |
| **Language(s)** | TypeScript |
| **Priority** | P1 |
| **Story points** | 4 |
| **Dependencies** | GOA-009 (Sprint 1) — Next.js app scaffold with chat UI shell and routing; GOA-048 (Sprint 1) — Exam service scaffold — FastAPI + exam_db + Academic/General split |

**Summary:** Exam preparation section of the frontend. Entry point for all 4 skills, Academic vs General Training toggle, and the shared exam shell all skill UIs live inside.

**Acceptance criteria:**

- New route /exam — landing page with Academic vs General Training toggle (persists in user profile), 4 skill cards (Reading/Listening/Speaking/Writing) each showing last band score and a Start Exam button
- Exam shell: full-screen layout, countdown timer top-right (turns red at 5 min remaining), skill name and exam type badge, Submit button with confirmation modal
- Timer: receives total_seconds from server, counts down client-side, sends heartbeat PATCH /sessions/:id/heartbeat every 60s
- Auto-submit: timer reaching 0 automatically submits current answers
- Exam state persisted in sessionStorage — page refresh resumes exam (re-fetches session from server)
- Results page: overall band score prominently, skill breakdown, Review Answers section with correct answers revealed
- Mobile responsive — minimum 768px (tablet) for exam mode
- Results state machine per skill — SPEAKING: in_progress → part1_done → part2_done → part3_done → evaluating (spinner 'Evaluating your exam...') → results. WRITING: task1_submitted → task1_evaluating → task1_done (side panel shown) → task2_writing → task2_submitted → task2_evaluating → combined_results. READING/LISTENING: submitted → results (instant, no spinner needed)
- Evaluating spinner for Speaking: full-screen overlay with animated waveform icon, message 'Analysing your performance across all 3 parts...' — blocks interaction until results ready
- Results page sections vary by skill: Speaking shows per-criterion cards with part-by-part narrative and quoted transcript examples; Writing shows Task 1 + Task 2 cards side-by-side with combined band; Reading/Listening shows per-question breakdown with correct answers revealed
- Improvement tips section on every results page: 3 specific, actionable tips based on weakest criterion/section — links to /exam to practice that skill again
- After exam completion: user's band scores written to their profile via Exam service internal endpoint — used by Orchestration for personalised recommendations (GOA-061)

**Implementation notes:**

Next.js client component. Full-screen via CSS position:fixed exam shell. useInterval hook for timer. sessionStorage stores {session_id, exam_type, skill_area} for resume.

**Tests / Definition of done:**

- E2E: start Reading exam, timer counts down, refresh page, exam resumes at correct remaining time
- E2E: timer reaches 0, auto-submit fires, result page shown with correct data
- E2E: Speaking exam — complete 3 parts, verify evaluating spinner shown after Part 3 submit, results appear with per-part narrative
- E2E: Writing exam — submit Task 1, verify results side panel appears while Task 2 editor remains active, submit Task 2, verify combined band shown
- E2E: Speaking exam — complete Part 3 — verify evaluating spinner appears and results page loads automatically
- E2E: Writing exam — submit Task 1 — verify Task 2 textarea is not disabled while Task 1 evaluation runs

---

---

### GOA-012 — Profile Matcher Agent — 3-stage scoring pipeline

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/xwS0IG8S

| | |
|---|---|
| **Service** | RAG |
| **Type** | AI/Agents |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 4 |
| **Dependencies** | GOA-006 (Sprint 1) — RAG service scaffold — FastAPI + pgvector + LangChain Python; GOA-004 (Sprint 1) — User service scaffold — NestJS with PostgreSQL and TypeORM |

**Summary:** Implement the full scoring system: Stage 1 hard gates (instant 0 on failure), Stage 2 weighted soft scoring, Stage 3 LLM contextual boost. Returns confidence score 0–100 with gap report.

**Acceptance criteria:**

- POST /score accepts {userId, programId} — returns ScoringResult
- Stage 1: check ECTS ≥ program minimum, degree level match, citizenship eligibility — any fail returns score=0 immediately with blockedBy reason
- Stage 2: normalise GPA (0–100), IELTS band (0–100), work_exp (0–100), extracurriculars (0–100) — weighted sum: 30% + 25% + 25% + 20%
- Stage 3: LLM call with full CV text + SOP → returns integer −10 to +10 with justification
- Final score = min(100, max(0, stage2_score + stage3_boost))
- Gap report: list of specific items to improve with actionable text
- POST /match accepts {userId} — returns top 10 programs ranked by score, filtered to score > 0
- Scoring result cached in Redis for 1 hour (same user + program = same score)
- Prometheus counter goa_scoring_hard_gate_blocks_total labelled by gate_type — tracks which gate blocks most users
- Prometheus histogram goa_scoring_latency_ms labelled by stage (stage1/stage2/stage3) — targets: stage1 <5ms, stage2 <10ms, stage3 <800ms
- Langfuse trace on Stage 3 LLM boost call — log boost value and justification
- Evaluation metric: 100% correct gate decisions on 20 synthetic profiles (run in CI)
- goa_scoring_hard_gate_blocks_total Prometheus counter with label: gate_type (ects|degree_level|citizenship|age|prerequisites)
- goa_scoring_latency_ms Prometheus histogram with label: stage (stage1|stage2|stage3) — measure each stage independently
- Stage 3 LLM boost creates Langfuse child span on parent trace: model, boost_value (int), justification_tokens, latency_ms
- goa_scoring_boost_value Prometheus histogram — distribution of LLM boost values over time
- Structured log per score: {user_id, program_id, stage1_passed, stage2_score, stage3_boost, final_score, blocked_by, latency_ms}

**Implementation notes:**

Three pure functions: check_hard_gates(), compute_soft_score(), get_llm_boost(). LLM boost uses claude-haiku to keep cost low. Gap report generated from Stage 1 failures + Stage 2 sub-scores below threshold. Redis cache key: f"score:{userId}:{programId}".

**Implementation reference:**

```python
def check_hard_gates(profile, program) -> GateResult:
    if profile.ects < program.min_ects:
        return GateResult(passed=False, reason=
            f"ECTS {profile.ects} below minimum {program.min_ects}")
    if profile.degree_level not in program.accepted_degrees:
        return GateResult(passed=False, reason="Degree level not accepted")
    return GateResult(passed=True)
```

**Tests / Definition of done:**

- Unit: ECTS=120 with min=180 returns score=0 and correct blockedBy
- Unit: all hard gates pass + soft scores = 72% + boost = +5 → final = 77
- Unit: gap report includes IELTS message when band < 6.5
- Integration: POST /match returns ranked list for test user
- Unit: ECTS gate failure increments goa_scoring_hard_gate_blocks_total{gate_type='ects'}
- Integration: score a profile then check Langfuse trace shows stage3 LLM span with boost_value attribute

---

---

### GOA-016 — User service — profile update events published to SQS

**Members:** Ahmed Dorgham · **Link:** https://trello.com/c/elRjBgSY

| | |
|---|---|
| **Service** | User |
| **Type** | Backend |
| **Language(s)** | TypeScript |
| **Priority** | P2 |
| **Story points** | 2 |
| **Dependencies** | GOA-004 (Sprint 1) — User service scaffold — NestJS with PostgreSQL and TypeORM; GOA-002 (Sprint 1) — Shared event schema contracts package |

**Summary:** Whenever a user profile is updated, publish a UserUpdated event to SQS so other services (especially RAG) can maintain their local snapshots.

**Acceptance criteria:**

- After successful PUT /users/:id/profile, publish UserUpdated event to SQS queue user-events
- Event payload includes: userId, updatedFields (array of changed field names), full profile snapshot
- Use AWS SDK SQS client (LocalStack in dev, real SQS in staging)
- SQS publish is fire-and-forget: profile update succeeds even if SQS publish fails (log error)
- Dead letter queue configured for failed deliveries
- Integration test confirms event appears on queue after profile update

**Implementation notes:**

NestJS EventEmitter triggers SQS publish after successful DB write. Use @aws-sdk/client-sqs. Wrap in try/catch — SQS failure should not fail the HTTP response. DLQ configured in LocalStack for local dev.

**Tests / Definition of done:**

- Unit: SQS client called with correct payload after profile update
- Unit: HTTP 200 returned even when SQS publish throws
- Integration: update profile → event visible on LocalStack SQS queue
- Unit: SQS publish failure does not throw — HTTP 200 still returned to caller, error logged to structured JSON

---

---

### GOA-015 — Real data source adapters — IELTS, universities, scholarships

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/3ZnhHg4x

| | |
|---|---|
| **Service** | Ingestion |
| **Type** | Data |
| **Language(s)** | Python |
| **Priority** | P1 |
| **Story points** | 4 |
| **Dependencies** | GOA-010 (Sprint 1) — Ingestion worker scaffold — scraper framework + chunking pipeline; GOA-006 (Sprint 1) — RAG service scaffold — FastAPI + pgvector + LangChain Python |

**Summary:** Implement the actual web scraping adapters for your core data sources. Connect them to the ingestion pipeline. Run first real ingestion and verify RAG quality.

**Acceptance criteria:**

- IELTSOrgAdapter: scrapes band descriptors, task types, and scoring criteria from ielts.org
- MastersPortalAdapter: scrapes program listings with requirements from mastersportal.eu (use Playwright for JS-rendered pages)
- DAADAdapter: scrapes German scholarship listings from daad.de
- CheveningAdapter: scrapes scholarship criteria from chevening.org
- Each adapter implements SourceAdapter.scrape() → list[Document] with metadata: {source, category, country, last_updated}
- First full ingestion run: >200 documents in vector DB
- RAG quality check: 10 test questions answered correctly from ingested data (manual eval)
- Scraping respects robots.txt and adds 1-2s delay between requests
- Structured log on completion: {docs_processed, docs_skipped, docs_failed, embedding_tokens_used, duration_s} — published to S3 as JSON report
- Prometheus counter goa_ingestion_docs_processed_total labelled by source and outcome (success/skip/fail)
- Alert via CloudWatch if failure rate >10% in any single run
- goa_ingestion_docs_processed_total Prometheus counter with labels: source, outcome (success|skip|fail)
- goa_ingestion_embedding_tokens_total Prometheus counter — tracks cumulative OpenAI embedding API cost
- goa_ingestion_run_duration_seconds Prometheus gauge — set to elapsed time at end of each run
- Structured completion report written to S3: {run_id, started_at, finished_at, sources: [{name, docs_processed, docs_skipped, docs_failed}], total_embedding_tokens, duration_s}
- CloudWatch alarm (defined in Terraform): if fail ratio > 10% of processed in one run then SNS alert to team email

**Implementation notes:**

Playwright for JS-heavy sites (Mastersportal). requests + BeautifulSoup for static sites. Each adapter is a separate Python class. Add exponential backoff on HTTP errors. Store raw HTML in S3 alongside processed documents for debugging.

**Tests / Definition of done:**

- Unit: each adapter returns correctly structured Document objects from fixture HTML
- Integration: full ingestion run completes without error and inserts >200 documents
- Quality eval: manually verify 10 queries return relevant results
- Integration: run ingestion on fixture data then verify completion report JSON written to S3 with correct structure
- Unit: a document that raises an exception increments goa_ingestion_docs_processed_total{outcome='fail'}

---

---

### GOA-072 — Terraform — Lambda functions, EventBridge rules, and S3 buckets

**Members:** Abdelrahman Amer Rekabi · **Link:** https://trello.com/c/8jmHVR5O

| | |
|---|---|
| **Service** | DevOps |
| **Type** | Infrastructure |
| **Language(s)** | TypeScript |
| **Priority** | P1 |
| **Story points** | 2 |
| **Dependencies** | GOA-070 (Sprint 1) — Terraform — RDS, RDS Proxy, ElastiCache, SQS, Secrets Manager, IAM, and observability modules |

**Summary:** Provision all serverless and storage resources in Terraform. Lambda functions for async workers, EventBridge cron rules, and S3 buckets for all file storage.

**Acceptance criteria:**

- Module: lambda — one function per worker: cv-processor (Python, S3 trigger), scholarship-matcher (Python, EventBridge trigger), notification-sender (TypeScript, SQS trigger). All use container images from ECR. Lambda Insights extension layer enabled on all.
- Module: eventbridge — rules: goa-weekly-ingestion (cron: 0 2 * * SUN, targets Ingestion Lambda), goa-daily-scholarship-match (cron: 0 8 * * *, targets Scholarship Matcher Lambda)
- S3 trigger on cv-processor Lambda: fires on s3:ObjectCreated events with prefix cvs/ in the writing-files bucket (CVs are stored under cvs/; essays are typed text in writing_db and are never extracted — see GOA-087)
- Module: s3 — buckets: goa-writing-files-{env} (CVs, essays, Task 1 images), goa-exam-audio-{env} (Listening MP3s), goa-ingestion-reports-{env} (weekly run reports), goa-eval-reports-{env} (CI eval results), goa-terraform-state (bootstrap bucket, created by bootstrap script)
- All S3 buckets: versioning enabled, server-side encryption (AES-256), public access blocked, lifecycle rules (delete non-current versions after 30 days)
- Lambda concurrency limits set in Terraform: cv-processor max 20, notification-sender max 50, scholarship-matcher max 5

**Implementation notes:**

Lambda functions packaged as container images (Dockerfile in each worker directory). aws_lambda_event_source_mapping for SQS → notification-sender. aws_s3_bucket_notification for S3 → cv-processor.

> [!NOTE]
> The two test lines below still reference the `essays/` prefix — this is stale. The acceptance criterion above (`cvs/` prefix) is correct: essays are typed text stored directly in `writing_db` and are never extracted; CVs live under `cvs/` (see GOA-087 downstream impacts). Implement and test against `cvs/`.

**Tests / Definition of done:**

- EventBridge rules visible in console with correct cron expressions
- Upload a test file to goa-writing-files-staging/essays/ — verify cv-processor Lambda invoked within 30 seconds
- S3 bucket policy confirms public access is blocked
- After apply: upload test file to goa-writing-files-staging/essays/ — verify CV Processor Lambda invoked within 30 seconds
- Security: verify all S3 buckets have block_public_acls = true in terraform state

---

---

### GOA-017 — RAG service — consume UserUpdated events and maintain local profile snapshot

**Members:** Ahmed Mounir · **Link:** https://trello.com/c/1K4XoYgQ

| | |
|---|---|
| **Service** | RAG |
| **Type** | Backend |
| **Language(s)** | Python |
| **Priority** | P2 |
| **Story points** | 2 |
| **Dependencies** | GOA-016 (Sprint 2) — User service — profile update events published to SQS; GOA-006 (Sprint 1) — RAG service scaffold — FastAPI + pgvector + LangChain Python |

**Summary:** The RAG service needs user profile data for scoring without making synchronous calls to the User service. Subscribe to UserUpdated SQS events and maintain a local read-optimised profile table.

**Acceptance criteria:**

- Background SQS consumer polls user-events queue every 5 seconds
- On UserUpdated event: upsert LocalUserProfile record in rag_db
- LocalUserProfile stores only scoring-relevant fields: userId, ects, gpa, ieltsScore, degreeLevel, targetCountries
- Profile used by POST /score without any call to User service
- Consumer runs as asyncio background task alongside FastAPI server
- Visibility timeout: 30s; on failure, message returns to queue after timeout
- Metric: consumer lag (time between event published and consumed) logged

**Implementation notes:**

Python SQS consumer using aiobotocore for async polling. Run as asyncio background task started in FastAPI lifespan event. LocalUserProfile SQLAlchemy model. Idempotent upsert via INSERT ... ON CONFLICT DO UPDATE.

**Tests / Definition of done:**

- Unit: LocalUserProfile correctly populated from UserUpdated event payload
- Integration: publish UserUpdated to LocalStack → local profile updated within 10s
- Integration: publish UserUpdated event with changed IELTS band — verify LocalUserProfile.ielts_score updated in rag_db within 15 seconds

---

---
