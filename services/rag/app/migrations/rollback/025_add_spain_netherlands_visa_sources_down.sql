-- GOA-109 rollback for 025. Does not delete visa_requirements rows already produced.
DELETE FROM visa_sources
WHERE issuing_body IN ('Spain MAEC Consular Services',
                       'Immigration and Naturalisation Service (IND)');
