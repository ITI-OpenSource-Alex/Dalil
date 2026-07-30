-- Rollback for 027_checklist_persistence

DROP INDEX IF EXISTS uq_checklist_item_states_checklist_item;
ALTER TABLE checklist_item_states ALTER COLUMN checklist_id DROP NOT NULL;
ALTER TABLE checklist_item_states DROP COLUMN IF EXISTS is_checked;

DROP INDEX IF EXISTS uq_checklists_user_program;
ALTER TABLE checklists DROP COLUMN IF EXISTS updated_at;
ALTER TABLE checklists DROP COLUMN IF EXISTS generated_by;
ALTER TABLE checklists DROP COLUMN IF EXISTS items;
