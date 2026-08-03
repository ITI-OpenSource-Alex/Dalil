-- TODO (GOA-115): Replace TRUNCATE with targeted DELETEs of only eval-owned rows 
-- (the 00000000-…-0001→…-0020 profile UUIDs and the eval program row).
DELETE FROM local_user_profiles WHERE user_id::text LIKE '00000000-%';
DELETE FROM program_requirements WHERE id = '99999999-9999-9999-9999-999999999999';

-- TODO (GOA-115): Move the eval program off UUID 11111111-... to a clearly eval-owned UUID 
-- (e.g. 99999999-9999-9999-9999-999999999999) to avoid colliding with TU Munich's actual row.
INSERT INTO program_requirements (id, university, country, degree_level, min_ects, min_gpa, min_ielts) VALUES ('99999999-9999-9999-9999-999999999999', 'Test Uni', 'Test Country', 'Master', 120, 3.0, 6.5);

DO $$ 
BEGIN 
    BEGIN 
        ALTER TABLE program_requirements ADD COLUMN min_work_experience INT; 
    EXCEPTION 
        WHEN duplicate_column THEN NULL; 
    END; 
END $$;

UPDATE program_requirements SET min_work_experience = 2 WHERE id = '99999999-9999-9999-9999-999999999999';

DO $$ 
BEGIN 
    BEGIN 
        ALTER TABLE local_user_profiles ADD COLUMN work_exp INT; 
        ALTER TABLE local_user_profiles ADD COLUMN extracurriculars INT; 
        ALTER TABLE local_user_profiles ADD COLUMN gpa_scale VARCHAR; 
    EXCEPTION 
        WHEN duplicate_column THEN NULL; 
    END; 
END $$;

INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000001', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000002', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000003', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000004', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000005', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000006', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000007', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000008', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000009', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000010', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000011', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000012', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000013', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000014', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000015', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000016', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000017', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000018', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000019', 130, 3.5, '4.0', 5.0, 'Master', 3, 80, '{}');
INSERT INTO local_user_profiles (user_id, ects, gpa, gpa_scale, ielts_score, degree_level, work_exp, extracurriculars, target_countries) VALUES ('00000000-0000-0000-0000-000000000020', 130, 3.5, '4.0', 7.0, 'Master', 3, 80, '{}');