import { AppDataSource } from './data-source';

const batchId = process.env.MIGRATION_BATCH_ID;
const direction = process.env.MIGRATION_DIRECTION === 'down' ? 'down' : 'up';

async function ensureBatchLedger(): Promise<void> {
  await AppDataSource.query(`
    CREATE TABLE IF NOT EXISTS migration_batches (
      batch_id VARCHAR(255) PRIMARY KEY,
      baseline_migration_id INTEGER NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
}

async function currentMigrationId(): Promise<number> {
  const exists = await AppDataSource.query(
    "SELECT to_regclass('public.migrations') AS table_name",
  );
  if (!exists[0]?.table_name) {
    return 0;
  }
  const rows = await AppDataSource.query(
    'SELECT COALESCE(MAX(id), 0)::int AS id FROM migrations',
  );
  return Number(rows[0]?.id ?? 0);
}

async function runUp(): Promise<void> {
  if (!batchId) {
    await AppDataSource.runMigrations();
    return;
  }

  await ensureBatchLedger();
  const baseline = await currentMigrationId();
  await AppDataSource.query(
    `
    INSERT INTO migration_batches (batch_id, baseline_migration_id)
    VALUES ($1, $2)
    ON CONFLICT (batch_id) DO NOTHING
    `,
    [batchId, baseline],
  );
  await AppDataSource.runMigrations();
}

async function runDown(): Promise<void> {
  if (!batchId) {
    throw new Error('MIGRATION_BATCH_ID is required for down migrations');
  }

  await ensureBatchLedger();
  const rows = await AppDataSource.query(
    'SELECT baseline_migration_id FROM migration_batches WHERE batch_id = $1',
    [batchId],
  );
  if (rows.length === 0) {
    return;
  }

  const baseline = Number(rows[0].baseline_migration_id);
  while ((await currentMigrationId()) > baseline) {
    await AppDataSource.undoLastMigration();
  }
  await AppDataSource.query('DELETE FROM migration_batches WHERE batch_id = $1', [
    batchId,
  ]);
}

async function main(): Promise<void> {
  await AppDataSource.initialize();
  try {
    if (direction === 'down') {
      await runDown();
    } else {
      await runUp();
    }
  } finally {
    await AppDataSource.destroy();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
