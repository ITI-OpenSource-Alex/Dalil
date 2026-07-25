-- GOA-109 rollback for 023.
--
-- Restores the UK source to the landing page (which publishes no amounts, so the UK
-- financial gap item becomes contentless again) and re-activates the four sources with
-- dead URLs (so each run resumes spending fetches on 404s). Both are regressions the
-- migration exists to fix — prefer fixing forward.

UPDATE visa_sources
SET source_url = 'https://www.gov.uk/student-visa'
WHERE country = 'United Kingdom'
  AND source_url = 'https://www.gov.uk/student-visa/money';

UPDATE visa_sources
SET active = TRUE
WHERE issuing_body IN (
    'Czech Embassy Cairo',
    'Campus France Egypt',
    'German Embassy Cairo',
    'Spanish Consulate Cairo'
);
