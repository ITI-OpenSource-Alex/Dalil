-- GOA-134 rollback.
--
-- Reverting requires every band_score to be non-null. Rows written while the
-- column was nullable -- sessions the swarm genuinely could not score -- have to
-- be resolved first, by re-evaluating or deleting them. Filling them with 0.0 to
-- make this statement succeed would reintroduce the exact defect GOA-134
-- removed, so it is deliberately not done here and this will fail loudly instead.
ALTER TABLE exam_results ALTER COLUMN band_score SET NOT NULL;
