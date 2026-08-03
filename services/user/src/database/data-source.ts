import { DataSource } from 'typeorm';
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

export const AppDataSource = new DataSource({
  type: 'postgres',
  ...databaseConnection,
  entities: [User, UserProfile, ResetToken, EmailVerification, RefreshToken],
  migrations: [__dirname + '/migrations/*.{js,ts}'],
  synchronize: false,
  logging: true,
});
