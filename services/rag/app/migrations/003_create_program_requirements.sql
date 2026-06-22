CREATE TABLE IF NOT EXISTS program_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    university VARCHAR(255) NOT NULL,
    country VARCHAR(100) NOT NULL,
    degree_level VARCHAR(100) NOT NULL,
    min_ects INTEGER NULL,
    min_gpa DECIMAL(4,2) NULL,
    min_ielts DECIMAL(3,1) NULL,
    citizenship_required VARCHAR(100) NULL
);