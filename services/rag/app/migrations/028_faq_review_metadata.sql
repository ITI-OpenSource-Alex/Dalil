-- GOA-045: give every FAQ entry a citation and an expiry, and re-curate the
-- seed set down to genuinely stable procedural content.
--
-- The FAQ short-circuit skips embedding, retrieval and the LLM, so a hit is a
-- promise that the curated text is still true. Nothing in the original schema
-- backed that promise: entries carried no source and no review date, so a
-- figure written once would be served forever with no way to tell how old it
-- was. This migration adds the two columns that make staleness detectable, and
-- removes the entries whose answers were never safe to freeze.

ALTER TABLE faq_entries
    -- Paraphrases of the canonical question. GOA-045 calls for "canonical
    -- question/aliases", and the calibration in docs/faq_threshold_calibration.md
    -- shows why: real users under-specify. "Whats a studienkolleg?" scores 0.77
    -- against the canonical wording and would miss at any threshold that also
    -- excludes unrelated questions. An alias widens recall for a known phrasing
    -- without lowering the bar for everything else.
    ADD COLUMN IF NOT EXISTS aliases TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS source_url TEXT,
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ,
    -- Per-entry rather than a single global constant: "what is a Studienkolleg"
    -- is safe for a year, while anything touching consular process deserves a
    -- shorter leash. Defaults to a year; tighten per row as needed.
    ADD COLUMN IF NOT EXISTS review_interval_days INTEGER NOT NULL DEFAULT 365;

-- The legacy seeds (migrations 012 and 018) are identified by their empty
-- sources array -- nothing curated through the GOA-045 admin endpoint can look
-- like this, because that endpoint requires a source_url. Removing rather than
-- back-filling is deliberate: roughly a third of them were time-sensitive
-- (visa fees, the Sperrkonto minimum, APS processing times, the 140-work-days
-- rule, IELTS score thresholds, the maximum age), and inventing a citation for
-- an answer that should not be cached at all would launder the problem instead
-- of fixing it. Those questions now go to live retrieval, where GOA-108's
-- evidence-backed visa data answers them with a current citation.
DELETE FROM faq_entries WHERE sources = '[]'::jsonb OR sources IS NULL;

-- The question is the natural key: re-asking it must update the entry, never
-- add a second one. Two near-identical rows would compete for the same fuzzy
-- match, and which one wins would depend on row order.
--
-- Created BEFORE the seed so the INSERT below can upsert on it. That ordering
-- is what makes this migration re-runnable: the service applies each file as a
-- single multi-statement execute, so a duplicate-key error rolls back
-- everything -- including the ALTER TABLE statements -- and leaves the table in
-- its old shape with the migration unrecorded.
CREATE UNIQUE INDEX IF NOT EXISTS idx_faq_question_pattern_unique
    ON faq_entries (question_pattern);

-- reviewed_at = NOW() because this migration IS the review event: the 30 rows
-- below were curated and source-checked as part of GOA-045. Re-review is a new
-- seed migration or an admin-endpoint update, both of which move the date.
INSERT INTO faq_entries
    (question_pattern, answer_markdown, sources, category, source_url, reviewed_at, review_interval_days)
VALUES
-- ============================ IELTS ==================================
(
    'How do I register for the IELTS exam in Egypt?',
    $$Register through an authorised test centre — in Egypt these are run by the British Council and IDP.

1. Choose **IELTS Academic** (university admission) or **General Training**.
2. Create an account on the test centre's booking site and pick a date and location.
3. Upload the identity document you will bring on test day. It must be the same one, and it must still be valid.
4. Pay the test fee to confirm the booking.
5. Bring that identical ID to the test centre — a mismatch means you are turned away.

Book several weeks ahead: seats in Cairo and Alexandria fill up, especially before university intake deadlines.$$,
    '[{"source_url": "https://www.ielts.org/", "title": "IELTS official site"}]'::jsonb,
    'exams', 'https://www.ielts.org/', NOW(), 365
),
(
    'What is the difference between IELTS Academic and IELTS General Training?',
    $$**Academic** is the version universities require for degree admission. **General Training** is for work and migration routes.

The Listening and Speaking sections are identical. Reading and Writing differ: Academic uses subject texts and asks you to describe a chart or diagram in Task 1, while General Training uses everyday texts and asks for a letter.

If you are applying to a Master's programme, you want Academic. Booking the wrong one means re-sitting and re-paying.$$,
    '[{"source_url": "https://www.ielts.org/", "title": "IELTS official site"}]'::jsonb,
    'exams', 'https://www.ielts.org/', NOW(), 365
),
(
    'What is the IELTS band scale and how is the overall score calculated?',
    $$Each of the four sections — Listening, Reading, Writing, Speaking — is scored from 0 to 9 in half-band steps.

The overall band is the **average of the four**, rounded to the nearest half band: an average ending in .25 rounds up to the next half band, and .75 rounds up to the next whole band.

Universities usually state both an overall minimum and a per-section minimum, so a strong average does not automatically satisfy a programme that requires 6.0 in every section.$$,
    '[{"source_url": "https://www.ielts.org/", "title": "IELTS official site"}]'::jsonb,
    'exams', 'https://www.ielts.org/', NOW(), 365
),
-- ============================ APS ====================================
(
    'What is an APS certificate?',
    $$The APS (Akademische Prüfstelle) is the academic evaluation office that verifies your degree documents before a German student visa can be issued.

It checks that your certificates are genuine and that your qualification matches what you claim. You submit your documents, the office reviews them, and you receive a certificate you then include in the visa application.

For Egyptian applicants the APS step comes **before** the visa appointment, so start it as early as you can.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'aps', 'https://kairo.diplo.de/', NOW(), 365
),
(
    'Does the APS certificate expire?',
    $$No. Once issued, the APS certificate does not have an expiry date and can be reused for later applications.

You only need a new one if the underlying qualification changes — for example if you finish a further degree and want that one evaluated too.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'aps', 'https://kairo.diplo.de/', NOW(), 365
),
(
    'What documents does the APS ask Egyptian applicants to submit?',
    $$Typically your school leaving certificate, your university degree certificate and full transcripts, your passport, and proof of language ability.

Documents usually need to be submitted as certified copies with translations. Requirements differ slightly by qualification, so confirm the current checklist on the embassy page before you post anything — a missing certified copy restarts the process.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'aps', 'https://kairo.diplo.de/', NOW(), 180
),
-- ============================ Visa process ===========================
(
    'How do I book a German student visa appointment through VFS Global Egypt?',
    $$1. Create an account on the VFS Global Egypt portal for Germany.
2. Select the **national (long-stay) student visa** category — not a Schengen short-stay one.
3. Pick a centre (Cairo or Alexandria) and the first available slot.
4. Complete the application form and upload the document checklist the portal generates.
5. Attend in person with the originals plus one photocopy set.

Slots are released in batches and go quickly. Book as soon as your APS certificate and admission letter are in hand.$$,
    '[{"source_url": "https://visa.vfsglobal.com/egy/en/deu/", "title": "VFS Global Egypt - Germany"}]'::jsonb,
    'visa_process', 'https://visa.vfsglobal.com/egy/en/deu/', NOW(), 180
),
(
    'Does VFS Egypt conduct the visa interview?',
    $$No. VFS is a service partner that collects documents and biometrics. It does not decide your application and does not conduct the assessment interview.

Your file is forwarded to the German Embassy or Consulate, which makes the decision. If an interview is needed, the mission arranges it — VFS staff cannot answer questions about the outcome.$$,
    '[{"source_url": "https://visa.vfsglobal.com/egy/en/deu/", "title": "VFS Global Egypt - Germany"}]'::jsonb,
    'visa_process', 'https://visa.vfsglobal.com/egy/en/deu/', NOW(), 180
),
(
    'Do I need to submit my original passport to VFS or the Embassy?',
    $$Yes. Your original passport is submitted with the application and stays with the mission while the visa is processed, because the visa sticker is placed inside it.

You get it back when the decision is made. Plan any other travel around this — you cannot use the passport while it is held.$$,
    '[{"source_url": "https://visa.vfsglobal.com/egy/en/deu/", "title": "VFS Global Egypt - Germany"}]'::jsonb,
    'visa_process', 'https://visa.vfsglobal.com/egy/en/deu/', NOW(), 180
),
(
    'What happens if my German student visa gets rejected?',
    $$You receive a written refusal setting out the reasons. There are two routes:

- **Remonstration** — a formal written objection to the same mission, asking it to reconsider. It must address the stated reasons point by point and is submitted within the deadline printed on the refusal.
- **A fresh application** — usually the faster route when the refusal was about missing or weak documents rather than a judgement about your intent.

Read the reasons carefully first. Re-submitting the same file unchanged produces the same result.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'visa_process', 'https://kairo.diplo.de/', NOW(), 180
),
(
    'Can I appeal a rejected German student visa through remonstration?',
    $$Yes. Remonstration is a written objection asking the mission to review its own decision.

Address every reason given in the refusal letter, attach whatever new evidence answers it, and submit within the deadline stated on the letter. A remonstration that simply repeats the original application rarely succeeds — its purpose is to correct or complete the record.

Many applicants find a corrected new application resolves the issue sooner, so weigh both routes.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'visa_process', 'https://kairo.diplo.de/', NOW(), 180
),
(
    'Can my spouse accompany me on a German student visa?',
    $$Yes, through family reunification. Your spouse applies for their own dependent visa rather than being added to yours.

The application generally requires a legalised marriage certificate, proof that you can support the family, and suitable accommodation. It is processed separately and can take longer than the student visa itself, so start it early if you intend to travel together.$$,
    '[{"source_url": "https://www.make-it-in-germany.com/en/", "title": "Make it in Germany (federal portal)"}]'::jsonb,
    'visa_process', 'https://www.make-it-in-germany.com/en/', NOW(), 180
),
(
    'Can I switch from a language course visa to a student visa inside Germany?',
    $$Often not. A visa issued purely for a language course is frequently marked as excluding a change of purpose, which means you must return home and apply for the student visa from Egypt.

If you intend to study a degree afterwards, apply for a **language course with the intent to study** (Sprachkurs zum Studium) category from the start. Confirm the wording on your own visa sticker and with the local Ausländerbehörde before making plans.$$,
    '[{"source_url": "https://www.make-it-in-germany.com/en/", "title": "Make it in Germany (federal portal)"}]'::jsonb,
    'visa_process', 'https://www.make-it-in-germany.com/en/', NOW(), 180
),
-- ============================ Documents ==============================
(
    'How do I authenticate my documents at the German embassy in Cairo?',
    $$Document authentication for Germany runs through the Egyptian Ministry of Foreign Affairs and then the German mission.

The usual order is: issuing authority certifies the document, the Egyptian MFA legalises it, and the German mission then authenticates the MFA stamp. Some documents also require a certified German or English translation.

Confirm the current chain on the embassy page first — a document authenticated in the wrong order has to be redone from the start.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'documents', 'https://kairo.diplo.de/', NOW(), 180
),
(
    'How do I legalize my Egyptian birth certificate for use in Germany?',
    $$Request a **computerised** birth certificate from the Civil Registry — handwritten extracts are usually not accepted.

Then follow the legalisation chain: Egyptian Ministry of Foreign Affairs, then authentication by the German mission. A certified translation into German is normally required.

Egypt is not part of the Hague Apostille Convention for this purpose, so an apostille alone does not replace this chain.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'documents', 'https://kairo.diplo.de/', NOW(), 180
),
(
    'Do I need to translate my documents into German, or is English acceptable?',
    $$It depends on who is reading them.

- **Universities**: English-taught programmes usually accept English documents.
- **uni-assist**: accepts German or English, per its own document rules.
- **Visa and authorities**: generally require certified **German** translations.

Where German is required it must be a certified translation by a sworn translator. Your own translation, however accurate, is not accepted.$$,
    '[{"source_url": "https://www.uni-assist.de/en/", "title": "uni-assist"}]'::jsonb,
    'documents', 'https://www.uni-assist.de/en/', NOW(), 365
),
(
    'Do male Egyptian applicants need a military status certificate to study abroad?',
    $$Yes. Egyptian men of conscription age normally need a military service certificate — completed, exempted, or postponed — before they can travel to study.

This is an Egyptian exit requirement rather than a German one, handled through the recruitment authority. It is separate from the visa file and frequently underestimated, so start it in parallel with your admission application.$$,
    '[{"source_url": "https://kairo.diplo.de/", "title": "German Embassy Cairo"}]'::jsonb,
    'documents', 'https://kairo.diplo.de/', NOW(), 180
),
(
    'Do I need a police clearance certificate from Egypt for my German student visa application?',
    $$A police clearance certificate (Certificate of Good Conduct, "fish w tashbih") is not part of the standard German student visa checklist, but individual missions can request one.

Check the checklist the VFS portal generates for your specific application. If it is requested, it typically needs the same legalisation chain as your other civil documents, which takes time.$$,
    '[{"source_url": "https://visa.vfsglobal.com/egy/en/deu/", "title": "VFS Global Egypt - Germany"}]'::jsonb,
    'documents', 'https://visa.vfsglobal.com/egy/en/deu/', NOW(), 180
),
-- ============================ Admission ==============================
(
    'What is uni-assist and when do I need to use it?',
    $$uni-assist is a central service that pre-evaluates international applications on behalf of many German universities: it checks your documents, converts your grades to the German scale, and forwards a complete file to the university.

Not every university uses it, and some use it only for certain programmes. Check each programme page: applying directly when uni-assist is required (or the reverse) means the application is not considered.

It charges a handling fee per application.$$,
    '[{"source_url": "https://www.uni-assist.de/en/", "title": "uni-assist"}]'::jsonb,
    'admission', 'https://www.uni-assist.de/en/', NOW(), 365
),
(
    'What is anabin and how do I check whether my university is recognised?',
    $$anabin is the German database of foreign qualifications, maintained by the KMK. It is what authorities consult to decide whether your institution and degree are recognised.

Look up your institution under "Institutionen" — a **H+** rating means recognised. Then look up your degree under "Hochschulabschlüsse".

Both your university and your specific degree need to appear correctly; an H+/- institution or an unlisted degree is usually the first thing to resolve, because the APS and visa steps depend on it.$$,
    '[{"source_url": "https://anabin.kmk.org/", "title": "anabin (KMK)"}]'::jsonb,
    'admission', 'https://anabin.kmk.org/', NOW(), 365
),
(
    'Is the Egyptian Thanaweya Amma certificate recognised for university admission in Germany?',
    $$On its own it is generally **not** treated as equivalent to the German Abitur for direct entry.

The usual routes are either completing one or two years of university study in Egypt before applying, or attending a Studienkolleg and passing the Feststellungsprüfung.

Check your exact case in anabin, since recognition depends on the certificate type and your subsequent study.$$,
    '[{"source_url": "https://anabin.kmk.org/", "title": "anabin (KMK)"}]'::jsonb,
    'admission', 'https://anabin.kmk.org/', NOW(), 365
),
(
    'What is a Studienkolleg?',
    $$A Studienkolleg is a one-year preparatory college for international students whose school leaving certificate is not considered equivalent to the German Abitur.

You take an entrance test, then follow a subject-stream course (for example T for technical subjects, M for medicine, W for economics) and finish with the Feststellungsprüfung. Passing it qualifies you to apply for a Bachelor's programme in that stream.$$,
    '[{"source_url": "https://www.study-in-germany.de/en/", "title": "Study in Germany (DAAD)"}]'::jsonb,
    'admission', 'https://www.study-in-germany.de/en/', NOW(), 365
),
(
    'What is the Feststellungsprufung (FSP)?',
    $$The Feststellungsprüfung is the assessment examination at the end of a Studienkolleg year. Passing it establishes that you are qualified to begin a Bachelor's degree in Germany.

It covers German plus the subjects of your Studienkolleg stream, and the stream you pass in determines which degree subjects you can then apply for. It is possible to sit it externally without attending a Studienkolleg, but that is considerably harder.$$,
    '[{"source_url": "https://www.study-in-germany.de/en/", "title": "Study in Germany (DAAD)"}]'::jsonb,
    'admission', 'https://www.study-in-germany.de/en/', NOW(), 365
),
(
    'What is the difference between conditional and unconditional admission?',
    $$**Unconditional** admission means the university has accepted you outright and issued the admission letter used for the visa.

**Conditional** admission means you are accepted subject to something outstanding — usually a language certificate or a final transcript. It states what must still be provided.

This matters for the visa: missions generally expect an unconditional letter, and a conditional one may not be enough on its own. Resolve the condition before booking your appointment where possible.$$,
    '[{"source_url": "https://www.study-in-germany.de/en/", "title": "Study in Germany (DAAD)"}]'::jsonb,
    'admission', 'https://www.study-in-germany.de/en/', NOW(), 365
),
(
    'What is a motivation letter and what should it contain?',
    $$A motivation letter (statement of purpose) explains why this programme, why this university, and why you.

It normally covers your academic background and how it prepares you for the specific curriculum, the modules or research groups that drew you to that department, and what you intend to do afterwards.

Keep it to roughly one page, tie every claim to something in your transcript or CV, and write a fresh one per programme — a generic letter reads as one.$$,
    '[{"source_url": "https://www.study-in-germany.de/en/", "title": "Study in Germany (DAAD)"}]'::jsonb,
    'admission', 'https://www.study-in-germany.de/en/', NOW(), 365
),
(
    'Is a motivation letter required for the German student visa application?',
    $$Usually yes, though it serves a different purpose from the university one. The mission uses it to understand your study plan and your intent to return.

Cover why you chose Germany and this programme, how it follows from your education so far, how your studies are financed, and what you plan to do after graduating. Keep it consistent with the rest of your file — contradictions between the letter and your documents are what draw questions.$$,
    '[{"source_url": "https://visa.vfsglobal.com/egy/en/deu/", "title": "VFS Global Egypt - Germany"}]'::jsonb,
    'visa_process', 'https://visa.vfsglobal.com/egy/en/deu/', NOW(), 180
),
-- ============================ Money (procedure only) =================
(
    'What is a Sperrkonto (blocked account) and how does it work?',
    $$A blocked account is a German bank account that demonstrates you can support yourself. You deposit a sum before the visa is issued, and once in Germany you may withdraw only a limited amount each month — which is what makes it "blocked".

The process: choose a provider, open the account online, transfer the funds, receive the confirmation, and include that confirmation in the visa application.

**The required balance and the monthly withdrawal limit are set by the authorities and change.** Check the current figures rather than relying on any cached number.$$,
    '[{"source_url": "https://www.make-it-in-germany.com/en/", "title": "Make it in Germany (federal portal)"}]'::jsonb,
    'finance_process', 'https://www.make-it-in-germany.com/en/', NOW(), 180
),
(
    'How do I open a blocked account for a German student visa?',
    $$1. Choose a provider recognised by the German missions.
2. Complete the online application and identity verification.
3. Transfer the required amount plus the provider's fee from your own or a sponsor's account.
4. Wait for the confirmation document — this is what the visa application needs.
5. Attach it to your visa file.

Allow a few weeks: international transfers from Egypt can be slow, and the confirmation is only issued once the funds clear. **Confirm the current required amount from an official source before transferring.**$$,
    '[{"source_url": "https://www.make-it-in-germany.com/en/", "title": "Make it in Germany (federal portal)"}]'::jsonb,
    'finance_process', 'https://www.make-it-in-germany.com/en/', NOW(), 180
),
(
    'Is health insurance required for the German student visa application?',
    $$Yes. Proof of health insurance is part of the application, and you cannot enrol at a German university without it.

Students are normally covered by statutory (public) insurance through a German provider. Travel insurance covering the period before your German cover begins is often requested as well.

Arrange this before the visa appointment — the confirmation is one of the documents collected.$$,
    '[{"source_url": "https://www.make-it-in-germany.com/en/", "title": "Make it in Germany (federal portal)"}]'::jsonb,
    'insurance', 'https://www.make-it-in-germany.com/en/', NOW(), 180
),
(
    'What is the difference between public and private health insurance for students in Germany?',
    $$**Public (statutory)** insurance is the standard route for students. It charges a fixed student rate, accepts you regardless of pre-existing conditions, and is accepted everywhere for enrolment.

**Private** insurance can be cheaper for some, but opting out of the statutory system as a student is generally **irreversible for the rest of your studies**, and some universities are stricter about accepting it for enrolment.

Most international students choose public. Treat the decision as permanent.$$,
    '[{"source_url": "https://www.make-it-in-germany.com/en/", "title": "Make it in Germany (federal portal)"}]'::jsonb,
    'insurance', 'https://www.make-it-in-germany.com/en/', NOW(), 180
)
ON CONFLICT (question_pattern) DO UPDATE SET
    answer_markdown      = EXCLUDED.answer_markdown,
    sources              = EXCLUDED.sources,
    category             = EXCLUDED.category,
    source_url           = EXCLUDED.source_url,
    reviewed_at          = EXCLUDED.reviewed_at,
    review_interval_days = EXCLUDED.review_interval_days;


-- Aliases for the phrasings users actually type. Deliberately conservative:
-- each is a paraphrase of the SAME question, never a related-but-different one.
-- An over-broad alias silently redirects a distinct question to the wrong
-- curated answer, and a wrong answer served with high confidence and zero
-- latency is the worst outcome this feature can produce.
UPDATE faq_entries SET aliases = a.aliases
FROM (VALUES
    ('How do I register for the IELTS exam in Egypt?',
     ARRAY['how do I register for IELTS', 'how do I sign up for IELTS', 'how to book IELTS test', 'IELTS registration']),
    ('What is the difference between IELTS Academic and IELTS General Training?',
     ARRAY['IELTS academic or general', 'which IELTS do I need', 'difference between IELTS academic and general']),
    ('What is the IELTS band scale and how is the overall score calculated?',
     ARRAY['how is IELTS scored', 'IELTS band score calculation', 'how is the IELTS overall band calculated']),
    ('What is an APS certificate?',
     ARRAY['what is APS', 'what is the APS', 'APS certificate meaning', 'what does APS mean']),
    ('Does the APS certificate expire?',
     ARRAY['APS expiry', 'is the APS certificate valid forever', 'does APS expire']),
    ('What documents does the APS ask Egyptian applicants to submit?',
     ARRAY['APS document checklist', 'what do I send to APS', 'documents for APS Egypt']),
    ('How do I book a German student visa appointment through VFS Global Egypt?',
     ARRAY['how do I book a visa appointment', 'VFS appointment booking', 'how to get a visa appointment in Egypt', 'book german visa appointment']),
    ('Does VFS Egypt conduct the visa interview?',
     ARRAY['does VFS interview me', 'who conducts the visa interview', 'is the interview at VFS']),
    ('Do I need to submit my original passport to VFS or the Embassy?',
     ARRAY['do they keep my passport', 'original passport for visa application', 'do I hand over my passport']),
    ('What happens if my German student visa gets rejected?',
     ARRAY['visa rejected what now', 'what to do if visa is refused', 'my student visa was rejected']),
    ('Can I appeal a rejected German student visa through remonstration?',
     ARRAY['what is remonstration', 'how do I appeal a visa refusal', 'can I appeal a visa rejection']),
    ('Can my spouse accompany me on a German student visa?',
     ARRAY['can my wife come with me', 'can my husband join me in Germany', 'family reunification student visa']),
    ('Can I switch from a language course visa to a student visa inside Germany?',
     ARRAY['change language visa to student visa', 'switch from language course to studies']),
    ('How do I authenticate my documents at the German embassy in Cairo?',
     ARRAY['document authentication Germany', 'how to authenticate documents', 'embassy document attestation Cairo']),
    ('How do I legalize my Egyptian birth certificate for use in Germany?',
     ARRAY['birth certificate legalization', 'legalize birth certificate Germany', 'computerised birth certificate']),
    ('Do I need to translate my documents into German, or is English acceptable?',
     ARRAY['do I need german translation', 'are english documents accepted', 'certified translation requirement']),
    ('Do male Egyptian applicants need a military status certificate to study abroad?',
     ARRAY['military service certificate', 'do I need military status to travel', 'military exemption to study abroad']),
    ('Do I need a police clearance certificate from Egypt for my German student visa application?',
     ARRAY['police clearance certificate', 'certificate of good conduct', 'do I need a criminal record certificate']),
    ('What is uni-assist and when do I need to use it?',
     ARRAY['what is uni-assist', 'do I need uni assist', 'uniassist explained']),
    ('What is anabin and how do I check whether my university is recognised?',
     ARRAY['what is anabin', 'is my university recognised in Germany', 'how to check anabin']),
    ('Is the Egyptian Thanaweya Amma certificate recognised for university admission in Germany?',
     ARRAY['is thanaweya amma accepted in Germany', 'is my egyptian high school certificate recognised']),
    ('What is a Studienkolleg?',
     ARRAY['what is a studienkolleg', 'whats a studienkolleg', 'studienkolleg meaning', 'what is studienkolleg']),
    ('What is the Feststellungsprufung (FSP)?',
     ARRAY['what is the FSP', 'what is feststellungsprufung', 'what is the assessment exam']),
    ('What is the difference between conditional and unconditional admission?',
     ARRAY['conditional admission meaning', 'difference between conditional and unconditional offer']),
    ('What is a motivation letter and what should it contain?',
     ARRAY['what is a motivation letter', 'how to write a motivation letter', 'statement of purpose contents']),
    ('Is a motivation letter required for the German student visa application?',
     ARRAY['do I need a motivation letter for the visa', 'is a motivation letter needed for visa']),
    ('What is a Sperrkonto (blocked account) and how does it work?',
     ARRAY['what is a blocked account', 'what is a sperrkonto', 'how does a blocked account work']),
    ('How do I open a blocked account for a German student visa?',
     ARRAY['how do I open a blocked account', 'how to open a sperrkonto', 'opening a blocked account']),
    ('Is health insurance required for the German student visa application?',
     ARRAY['do I need health insurance for the visa', 'is health insurance mandatory for students']),
    ('What is the difference between public and private health insurance for students in Germany?',
     ARRAY['public or private health insurance', 'which health insurance should students choose'])
) AS a(question_pattern, aliases)
WHERE faq_entries.question_pattern = a.question_pattern;

-- Now that every surviving row has both, make the invariant structural rather
-- than a convention: an entry with no citation and no review date cannot
-- express when it stops being trustworthy, which is the whole point.
ALTER TABLE faq_entries
    ALTER COLUMN source_url SET NOT NULL,
    ALTER COLUMN reviewed_at SET NOT NULL;

ALTER TABLE faq_entries
    DROP CONSTRAINT IF EXISTS faq_entries_source_url_not_blank;
ALTER TABLE faq_entries
    ADD CONSTRAINT faq_entries_source_url_not_blank CHECK (btrim(source_url) <> '');

ALTER TABLE faq_entries
    DROP CONSTRAINT IF EXISTS faq_entries_review_interval_positive;
ALTER TABLE faq_entries
    ADD CONSTRAINT faq_entries_review_interval_positive CHECK (review_interval_days > 0);

-- The staleness filter runs on every query that reaches the FAQ path, so it
-- should not be a sequential scan once this table grows.
CREATE INDEX IF NOT EXISTS idx_faq_reviewed_at ON faq_entries (reviewed_at);

-- No index on `aliases` on purpose.
--
-- The obvious one -- gin (array_to_string(aliases, ' ') gin_trgm_ops) -- is
-- rejected: array_to_string is not IMMUTABLE, and Postgres will not build an
-- index on it. That matters more than it looks, because this service applies
-- migrations as a single multi-statement execute, so one failing statement
-- rolls the whole file back and the FAQ table would silently keep its old shape.
--
-- It would not have earned its keep anyway. The query scores each row with
-- word_similarity() rather than the <% operator, so it plans as a scan either
-- way. This table is curated by hand and sized in the tens; a scan over 30 rows
-- is cheaper than maintaining an index that the planner ignores. Revisit if the
-- table ever reaches thousands of entries, at which point the query should move
-- to the <% operator so an index can actually be used.
