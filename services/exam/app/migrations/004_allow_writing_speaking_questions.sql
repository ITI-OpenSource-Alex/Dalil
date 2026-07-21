-- Migration 004: Allow 'writing' and 'speaking' in questions.skill_area
-- The CHECK constraint on skill_area currently only permits ('reading', 'listening').
-- This migration drops the old constraint and adds a new one that also allows
-- 'writing' and 'speaking', matching the exam_sessions and exam_results tables.

ALTER TABLE questions
    DROP CONSTRAINT IF EXISTS questions_skill_area_check;

ALTER TABLE questions
    ADD CONSTRAINT questions_skill_area_check
    CHECK (skill_area IN ('reading', 'listening', 'writing', 'speaking'));
