-- GOA-111 rollback: revert canonical country names to the pre-021 spellings.
--
-- LOSSY: this restores only the specific mappings 021 applied. Rows created after 021
-- using the canonical spelling are indistinguishable from rows it renamed, so this
-- will also rename those. Reverting re-breaks the visa/program country join that
-- feeds the Profile Matcher's financial gap items — that regression is the point of
-- the migration, so prefer fixing forward over rolling back.

UPDATE visa_sources SET country = 'UK' WHERE country = 'United Kingdom';
UPDATE visa_requirements SET country = 'UK' WHERE country = 'United Kingdom';
