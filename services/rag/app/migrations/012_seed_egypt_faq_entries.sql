-- Seed 6 hand-curated, Egypt-specific FAQ entries (GOA-086).
-- These rows satisfy the "6 FAQ entries seeded" acceptance criterion only. They are not
-- yet reachable at query time -- no code checks faq_entries before answering a question;
-- that fuzzy-match-then-skip-LLM logic is GOA-045's scope (unimplemented). See the main
-- implementation plan's Dependencies section and Question #1.

INSERT INTO faq_entries (question_pattern, answer_markdown, sources, category) VALUES
(
    'Do I need an APS certificate to apply for a German student visa from Egypt?',
    $$Yes. Egyptian applicants to most German universities must obtain an APS certificate
(Akademische Prüfstelle) from APS Cairo before applying for a student visa. APS verifies
the authenticity of your secondary-school and university certificates and, where
applicable, conducts a short interview or reviews your academic file.

**Who needs it:** Almost all Egyptian nationals applying for a German university place,
whether for a Bachelor's, Master's, or PhD program. A small number of institutions and
scholarship programs (e.g. certain DAAD-funded placements) waive the requirement --
always confirm with your specific university or scholarship provider.

**Process overview:**
1. Prepare certified copies of your academic certificates and transcripts.
2. Submit your application and required documents to APS Cairo.
3. Attend an interview or document review, depending on your academic background.
4. Receive your APS certificate, which you then submit alongside your German university
   application and, later, your visa application.

Start the APS process early -- it commonly takes several weeks to a few months, and your
visa application cannot proceed without it.$$,
    '[]'::jsonb,
    'visa_egypt'
),
(
    'How much money do I need in my Sperrkonto (blocked account) for a German student visa?',
    $$A blocked account (Sperrkonto) is the standard way Egyptian students prove they can
cover their living costs in Germany for a full year. German authorities set and
periodically adjust the required minimum balance, so always confirm the current figure
with the German Embassy Cairo or your blocked-account provider (e.g. Fintiba) before
transferring funds -- do not rely on an outdated number.

**How it works:**
- You open a blocked account with an approved provider before your visa appointment.
- You transfer the full required annual amount into the account.
- Once your visa is approved and you arrive in Germany, you can withdraw a fixed monthly
  portion (roughly one-twelfth of the total) rather than the full sum at once.

**Egypt-specific notes:**
- Funds are usually transferred from Egypt in EGP and converted to EUR by your bank or
  the account provider -- confirm the exchange process and any transfer limits with your
  Egyptian bank in advance, since large international transfers can require additional
  documentation.
- A sponsor letter (Verpflichtungserklärung) from a financially qualified sponsor is
  sometimes accepted instead of a blocked account -- check with the embassy whether this
  option applies to your case before setting up a Sperrkonto.$$,
    '[]'::jsonb,
    'visa_egypt'
),
(
    'Is the Egyptian Thanaweya Amma certificate recognized for university admission in Germany?',
    $$The Thanaweya Amma (Egyptian General Secondary Education Certificate) is recognized
by German universities, but whether it grants **direct** admission or requires a
preparatory year depends on your final score and your intended field of study.

**General rule of thumb:**
- A high overall percentage (commonly cited around the low-to-mid 80s or above, though
  exact thresholds vary by state and university) may grant direct university entrance
  qualification.
- A lower score, or a mismatch between your Thanaweya Amma track (e.g. literary vs.
  scientific) and your intended degree, often means you must first complete a
  Studienkolleg (foundation course) and pass the Feststellungsprüfung assessment exam
  before starting your degree.

**What to do:**
1. Have your certificate evaluated by APS Cairo as part of your APS certification process.
2. Use uni-assist or your target university's own admissions office to confirm exactly
   how your specific Thanaweya Amma score and track are assessed for your chosen program,
   since requirements differ between universities and states (Bundesländer).

Because recognition rules can change and vary by institution, always verify your specific
case directly with APS Cairo and your target university rather than relying on a general
percentage rule alone.$$,
    '[]'::jsonb,
    'visa_egypt'
),
(
    'Do I need a police clearance certificate (Certificate of Good Conduct) from Egypt for my student visa application?',
    $$Many destination countries require a police clearance certificate (also called a
Certificate of Good Conduct or criminal record certificate) as part of a student visa or
residence permit application, particularly for longer stays. Requirements vary by
destination country, so confirm with the specific embassy or consulate before you apply.

**How to obtain it in Egypt:**
1. Apply through the Egyptian Ministry of Interior (in person, or in some cases via an
   authorized online portal), providing your national ID and passport details.
2. Processing typically takes from a few days up to a few weeks -- apply well before your
   visa appointment.
3. The certificate is usually issued in Arabic and must be officially translated into the
   destination country's language (English, German, French, etc.) by a certified
   translator.
4. Depending on the destination country, the certificate and its translation may also
   need legalization or an apostille before submission.

Because validity periods for these certificates are often short (commonly around 3-6
months, depending on the receiving country's rules), time the application so the
certificate is still valid when you submit your visa application.$$,
    '[]'::jsonb,
    'visa_egypt'
),
(
    'How do I book a visa appointment through VFS Global Egypt?',
    $$VFS Global operates outsourced visa application centres in Egypt on behalf of several
countries (including, depending on the destination, some Schengen states). If your
destination country's visa process is routed through VFS Global rather than directly
through the embassy, you will typically follow this process:

1. **Register online** on the VFS Global Egypt portal for your specific destination
   country -- each country has its own dedicated application section, since VFS serves
   many countries simultaneously.
2. **Complete the online application form** and upload the required supporting documents
   (passport, photos, financial proof, university acceptance letter, APS certificate
   where relevant, etc.) as specified for your destination country and visa type.
3. **Book an appointment** at the Cairo (or, where available, Alexandria) VFS Global
   application centre. Appointment slots can be limited, especially during peak
   application season, so book as early as your documents allow.
4. **Attend in person** to submit biometrics (fingerprints and photo) and your physical
   documents, and pay the visa fee plus the VFS service fee.
5. **Track your application** online using the reference number provided at submission.

Since VFS Global's exact document checklist and fees differ by destination country,
always check the specific country section of the VFS Global Egypt website rather than
assuming the process is identical across countries.$$,
    '[]'::jsonb,
    'visa_egypt'
),
(
    'Do male Egyptian applicants need a military status certificate to study abroad?',
    $$Egyptian men within the conscription-eligible age range generally need to resolve or
document their military service status before traveling abroad for extended study, since
this can affect both your Egyptian passport/travel permissions and some destination
countries' visa document checklists.

**Typical options:**
- **Postponement (Ta'agil):** Students accepted onto a recognized course of study can
  usually apply for a military service postponement for the duration of their studies,
  obtained through the Egyptian Ministry of Defense / recruitment office.
- **Exemption or completed service:** If you have already completed your military
  service, or qualify for an exemption, you can request a certificate confirming this
  status.

**What to do:**
1. Contact your local recruitment office (maktab al-tajneed) as soon as you have a
   confirmed university acceptance to start the postponement process -- this can take
   time, so begin well before your intended travel date.
2. Keep the resulting military status certificate with your other official documents, as
   some visa applications and Egyptian passport/travel-permission procedures may request
   it.

Requirements and procedures can change, so confirm the current process directly with the
Egyptian Ministry of Defense recruitment office for your governorate rather than relying
on outdated guidance.$$,
    '[]'::jsonb,
    'visa_egypt'
);
