-- Rename the column to match our Python Pydantic schema
ALTER TABLE program_requirements RENAME COLUMN citizenship_required TO required_citizenship;

-- Add the missing work experience column
ALTER TABLE program_requirements ADD COLUMN min_work_experience INTEGER NULL;

-- Seed some mock programs for local testing
INSERT INTO program_requirements (id, university, country, degree_level, min_ects, min_gpa, min_ielts, required_citizenship, min_work_experience)
VALUES
('11111111-1111-1111-1111-111111111111', 'Technical University Munich', 'Germany', 'Master', 120, 3.0, 6.5, NULL, 0),
('22222222-2222-2222-2222-222222222222', 'ETH Zurich', 'Switzerland', 'Master', 150, 3.5, 7.0, NULL, 2),
('33333333-3333-3333-3333-333333333333', 'Erasmus Mundus', 'Europe', 'Master', 120, 3.2, 6.5, 'EU', 0);