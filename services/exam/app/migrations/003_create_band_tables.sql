CREATE TABLE IF NOT EXISTS band_conversion_tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_area VARCHAR(20) NOT NULL,
    exam_type VARCHAR(20) NOT NULL,
    conversion JSONB NOT NULL,
    UNIQUE(skill_area, exam_type)
);
