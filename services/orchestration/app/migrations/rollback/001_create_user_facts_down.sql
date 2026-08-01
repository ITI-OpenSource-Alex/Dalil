-- Rollback for 001_create_user_facts
--
-- Local development only. `user_facts` holds personal data that a user may have
-- spent several sessions building up, and dropping it in a deployed environment
-- is a data-loss event, not a rollback. To disable the feature in staging or
-- production set MEMORY_ENABLED=false and redeploy -- the table stays, unread.

DROP INDEX IF EXISTS user_facts_user_reinforced_idx;
DROP INDEX IF EXISTS user_facts_identity_uniq;
DROP TABLE IF EXISTS user_facts;

DELETE FROM migrations_log WHERE migration_file = '001_create_user_facts.sql';
