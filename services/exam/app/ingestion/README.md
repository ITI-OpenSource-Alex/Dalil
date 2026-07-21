# Exam ingestion

This ingestion module intentionally extends the existing question table and repository pattern.
It keeps SQL inside the repository layer and leaves session, grading, timer, and exam workflow unchanged.

TODOs:
- Speaking and writing ingestion remain out of scope for this ticket until the downstream schemas and content format are defined.
- Actual S3 audio upload is deferred; the loader currently stores only the S3 key pattern for listening tests.
