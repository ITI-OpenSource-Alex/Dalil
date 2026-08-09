ALTER TABLE local_user_profiles
  ADD COLUMN IF NOT EXISTS ielts_listening DECIMAL(3,1),
  ADD COLUMN IF NOT EXISTS ielts_reading DECIMAL(3,1),
  ADD COLUMN IF NOT EXISTS ielts_writing DECIMAL(3,1),
  ADD COLUMN IF NOT EXISTS ielts_speaking DECIMAL(3,1);