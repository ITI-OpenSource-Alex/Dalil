import { DataSource } from 'typeorm';
import { User } from '../users/entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import * as dotenv from 'dotenv';
import { ResetToken } from 'src/users/entities/reset-tokens.entity';
import { EmailVerification } from 'src/users/entities/email-verification.entity';

// Load environment variables for CLI usage
dotenv.config();

export const AppDataSource = new DataSource({
  type: 'postgres',
  host: process.env.DB_HOST || 'localhost',
  port: parseInt(process.env.DB_PORT || '5432', 10),
  username: process.env.DB_USER || 'postgres',
  password: process.env.DB_PASSWORD || 'postgres',
  database: process.env.DB_NAME || 'user_db',
  entities: [User, UserProfile, ResetToken, EmailVerification],
  migrations: [__dirname + '/migrations/*.{js,ts}'],
  synchronize: false,
  logging: true,
});
