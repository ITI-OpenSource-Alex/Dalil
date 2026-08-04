DROP TABLE IF EXISTS ingestion_runs, crawl_sources, crawl_urls, crawl_cursors CASCADE;
DELETE FROM migrations_log WHERE migration_file = '001_initial_schema.sql';
