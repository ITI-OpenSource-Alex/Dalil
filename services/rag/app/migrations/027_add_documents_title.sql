-- Migration 027: Add title column to documents table for source citations
ALTER TABLE documents ADD COLUMN IF NOT EXISTS title VARCHAR(512) DEFAULT NULL;

-- Backfill title deterministically from category and source_url for existing rows
UPDATE documents 
SET title = CASE
    WHEN category = 'visa' THEN 'Official Visa & Immigration Guidance'
    WHEN category = 'language_requirements' THEN 'Official IELTS Scoring & Format Guide'
    WHEN category = 'scholarships' THEN 'Scholarship Program Documentation'
    WHEN source_url LIKE '%mastersportal.com%' THEN 'MastersPortal Program Listing'
    ELSE NULL
END
WHERE title IS NULL;