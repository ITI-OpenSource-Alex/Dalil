## Verification

- [ ] Service tests were run for the changed service(s).
- [ ] If this PR adds a migration, the matching down migration was run in local Docker and returned the schema to the previous state without errors.
- [ ] If this PR changes deploy behavior, the staging deploy path was exercised or the reason it could not be exercised is recorded.
- [ ] If this PR changes production promotion, the approval gate, same-image SHA check, smoke-test rollback, and Gateway-based staging E2E evidence are recorded.
