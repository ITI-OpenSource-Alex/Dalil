# GOA-030 — one-off catalogue seeder for a deployed environment.
#
# RDS sits in a private data subnet with PubliclyAccessible=false, so the
# catalogue cannot be loaded from a developer machine. It has to be loaded from
# inside the VPC, which means a container.
#
# The dump is BAKED INTO THE IMAGE rather than fetched at runtime, because the
# postgres image has psql but no curl, no wget and no python3 -- verified, not
# assumed -- so a container that pulls from S3 would first have to install a
# package manager's worth of tooling over the NAT gateway. At 16 MB compressed
# the dump is smaller than that tooling would be.
#
# Data-only: schema and the pgvector extension come from the services' own
# migrations, which must have run first.
FROM postgres:15

COPY rag_seed.sql.gz /seed/rag_seed.sql.gz

# ON_ERROR_STOP is the difference between a seeded database and a half-seeded
# one that reports success. Without it psql prints errors and exits 0, and the
# load test would then measure a catalogue with an unknown number of rows in it.
CMD ["sh", "-c", "gunzip -c /seed/rag_seed.sql.gz | psql -v ON_ERROR_STOP=1 \"$SEED_DATABASE_URL\""]
