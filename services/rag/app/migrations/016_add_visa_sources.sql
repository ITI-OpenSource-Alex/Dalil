-- GOA-116: Add visa_sources config table and extraction_evidence to visa_requirements.
-- The generic VisaSourceAdapter reads this table instead of shipping one bespoke
-- scraper class per embassy site.
--
-- NOTE: the rollback for this migration lives in migrations/rollback/, NOT here.
-- The runner globs migrations/*.sql and executes every match in sorted order, so a
-- "*_down.sql" file sitting beside this one gets executed as a migration immediately
-- after it — creating the table and then dropping it in the same startup.

CREATE TABLE IF NOT EXISTS visa_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country VARCHAR(100) NOT NULL,
    visa_type VARCHAR(100) NOT NULL,
    issuing_body VARCHAR(255) NOT NULL,
    source_url TEXT NOT NULL,
    fetch_method VARCHAR(50) NOT NULL DEFAULT 'httpx',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_fetched_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(country, visa_type, issuing_body)
);

-- The 9 sources GOA-086 specified. VFS Global is the one JS-rendered source and the
-- only row using the playwright fetch path.
INSERT INTO visa_sources (country, visa_type, issuing_body, source_url, fetch_method) VALUES
    ('Germany', 'National Visa (Study)', 'German Embassy Cairo', 'https://cairo.diplo.de/eg-en/service/05-VisaEinreise/-/2102148', 'httpx'),
    ('Germany', 'Academic Credential Verification', 'APS Cairo', 'https://aps-egypt.de/', 'httpx'),
    ('France', 'Long-stay Visa (Study)', 'Campus France Egypt', 'https://www.egypte.campusfrance.org/visa-long-sejour-etudiant', 'httpx'),
    ('United Kingdom', 'Student Visa', 'UK Visas and Immigration', 'https://www.gov.uk/student-visa', 'httpx'),
    ('Egypt', 'Biometric Appointment', 'VFS Global Egypt', 'https://visa.vfsglobal.com/egy/en/', 'playwright'),
    ('Germany', 'Blocked Account', 'Fintiba', 'https://www.fintiba.com/blocked-account/', 'httpx'),
    ('Czech Republic', 'Long-term Visa (Study)', 'Czech Embassy Cairo', 'https://mzv.gov.cz/cairo/en/visas_and_consular_information/long_term_visa/study.html', 'httpx'),
    ('Spain', 'National Visa (Study)', 'Spanish Consulate Cairo', 'https://www.exteriores.gob.es/Consulados/elcairo/en/ServiciosConsulares/Paginas/index.aspx', 'httpx'),
    ('Italy', 'National Visa (Study)', 'Italian Embassy Cairo', 'https://ambcairo.esteri.it/en/servizi-consolari-e-visti/servizi-per-il-cittadino-straniero/visti/', 'httpx')
ON CONFLICT (country, visa_type, issuing_body) DO NOTHING;

-- Per-field verbatim evidence quotes backing every extracted value, so a reviewer can
-- confirm the model quoted the fetched page rather than answering from memory.
ALTER TABLE visa_requirements ADD COLUMN IF NOT EXISTS extraction_evidence JSONB;

-- NOTE: the 6 Egypt-specific FAQ seed entries this ticket references are already seeded
-- by 012_seed_egypt_faq_entries.sql (GOA-086) and are deliberately NOT re-seeded here.
