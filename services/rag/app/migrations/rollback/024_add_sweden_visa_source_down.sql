-- GOA-109 rollback for 024: remove the Sweden visa source.
-- Removing the source does not delete any visa_requirements row it already produced;
-- delete that separately if a full revert is intended.

DELETE FROM visa_sources
WHERE issuing_body = 'Swedish Migration Agency'
  AND source_url = 'https://www.migrationsverket.se/en/you-want-to-apply/study/higher-education.html';
