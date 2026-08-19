-- The live Speaking service owns the adaptive interview bank. Exam still needs
-- a question row to create an owned/timed attempt because exam_sessions has a
-- required question_id. These non-empty anchors make both IELTS variants
-- startable without pretending the Exam database owns the live questions.
INSERT INTO questions (
    id, book_ref, test_number, exam_type, skill_area,
    passage_text, audio_s3_key, questions, answer_key
)
VALUES
(
    '3132be6f-6b51-4ada-a9d3-3f72bf4561a1',
    'speaking-adaptive-v1-academic', 1, 'academic', 'speaking',
    NULL, NULL,
    '[{"type":"adaptive_interview","parts":[1,2,3]}]'::jsonb,
    '{}'::jsonb
),
(
    '3132be6f-6b51-4ada-a9d3-3f72bf4561a2',
    'speaking-adaptive-v1-general', 1, 'general', 'speaking',
    NULL, NULL,
    '[{"type":"adaptive_interview","parts":[1,2,3]}]'::jsonb,
    '{}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
    book_ref = EXCLUDED.book_ref,
    questions = EXCLUDED.questions;
