CREATE TABLE IF NOT EXISTS local_user_profiles (
    user_id UUID PRIMARY KEY,
    degree_level VARCHAR(100) NULL,
    gpa DECIMAL(4,2) NULL,
    ielts_score DECIMAL(3,1) NULL,
    target_countries TEXT[] NULL,
    field_of_study VARCHAR(255) NULL,
    ects INTEGER NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);