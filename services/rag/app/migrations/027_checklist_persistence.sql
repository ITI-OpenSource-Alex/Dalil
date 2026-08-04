-- GOA-084: checklist persistence.
--
-- 006_add_checklists.sql (applied in every environment already, so it must be
-- altered forward rather than edited) created a placeholder schema shaped one
-- row per item (title/description/category) with no uniqueness guarantee on
-- (user_id, program_id). This ticket needs one checklist row per user+program
-- carrying its generated items as JSON, plus per-item checked state keyed by
-- item_key. Alter the placeholder tables into that shape.

-- Placeholder-era rows predate the uniqueness rules below and would violate
-- them; there is no real checklist data yet in any environment, so clearing
-- it is safe.
DELETE FROM checklist_item_states;
DELETE FROM checklists;

ALTER TABLE checklists ADD COLUMN IF NOT EXISTS items JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS generated_by VARCHAR(20) NOT NULL DEFAULT 'llm';
ALTER TABLE checklists ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- Enforces "do not regenerate on every request" at the database level: a
-- concurrent INSERT ... ON CONFLICT DO NOTHING against this index is what
-- makes the get-or-create race safe.
CREATE UNIQUE INDEX IF NOT EXISTS uq_checklists_user_program
    ON checklists (user_id, program_id);

ALTER TABLE checklist_item_states ADD COLUMN IF NOT EXISTS is_checked BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE checklist_item_states ALTER COLUMN checklist_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_checklist_item_states_checklist_item
    ON checklist_item_states (checklist_id, item_key);
