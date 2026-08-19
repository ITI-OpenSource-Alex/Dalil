import { DataSource } from 'typeorm';
import { readFileSync } from 'fs';
import { User } from '../users/entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import * as dotenv from 'dotenv';
import { ResetToken } from '../users/entities/reset-tokens.entity';
import { EmailVerification } from '../users/entities/email-verification.entity';
import { RefreshToken } from '../users/entities/refresh-token.entity';

// Load environment variables for CLI usage
dotenv.config();

const databaseConnection = process.env.DATABASE_URL
  ? { url: process.env.DATABASE_URL }
  : {
      host: process.env.DB_HOST || 'localhost',
      port: parseInt(process.env.DB_PORT || '5432', 10),
      username: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || 'postgres',
      database: process.env.DB_NAME || 'user_db',
    };

/**
 * TLS for managed Postgres (GOA-030).
 *
 * RDS presents a certificate signed by an Amazon CA that is not in Node's
 * bundled trust store, so every migration against it died with
 * `SELF_SIGNED_CERT_IN_CHAIN` before running a single statement. Locally this
 * never appears: docker-compose Postgres speaks plaintext.
 *
 * It is also why this service failed alone. The Python services reach the same
 * database through asyncpg, which defaults to sslmode=prefer and does not
 * verify the chain, so they connected happily while this one could not -- which
 * reads like a user-service bug rather than a missing CA.
 *
 * The fix is supplying the CA, not disabling the check: point PGSSLROOTCERT or
 * NODE_EXTRA_CA_CERTS at the RDS global bundle and the chain verifies properly.
 * DB_SSL_INSECURE exists for a developer poking at a managed database by hand,
 * and is deliberately opt-in and named for what it does -- accepting any
 * certificate on a database connection means accepting any server.
 */
const sslRootCert = process.env.PGSSLROOTCERT || process.env.NODE_EXTRA_CA_CERTS;
const ssl =
  process.env.DB_SSL_INSECURE === 'true'
    ? { rejectUnauthorized: false }
    : sslRootCert
      ? { ca: readFileSync(sslRootCert, 'utf-8'), rejectUnauthorized: true }
      : undefined;

export const AppDataSource = new DataSource({
  type: 'postgres',
  ...databaseConnection,
  ...(ssl ? { ssl } : {}),
  entities: [User, UserProfile, ResetToken, EmailVerification, RefreshToken],
  migrations: [__dirname + '/migrations/*.{js,ts}'],
  synchronize: false,
  logging: true,
});
