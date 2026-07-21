/**
 * Jest global setup file for E2E tests.
 *
 * This runs in the Jest worker process BEFORE any test module is imported,
 * which means it fires before:
 *   - AppModule is compiled
 *   - data-source.ts executes its top-level `new DataSource(...)` call
 *   - SqsModule.registerAsync() runs its useFactory
 *
 * We load test/.env.e2e here so every process.env access in production code
 * receives the correct E2E values without touching any source file.
 */
import * as dotenv from 'dotenv';
import * as path from 'path';

dotenv.config({ path: path.resolve(__dirname, '.env.e2e') });
