import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  OneToOne,
  OneToMany,
  Index,
} from 'typeorm';
import { UserProfile } from '../../profile/entities/profile.entity';
import { ResetToken } from './reset-tokens.entity';
import { EmailVerification } from './email-verification.entity';
import { RefreshToken } from './refresh-token.entity';
@Entity('users')
export class User {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Index({ unique: true })
  @Column({ unique: true })
  email: string;

  @Column()
  passwordHash: string;

  @Column({
    type: 'varchar',
    default: 'free',
  })
  subscriptionTier: 'free' | 'paid';

  @CreateDateColumn({ type: 'timestamp' })
  createdAt: Date;

  @OneToOne(() => UserProfile, (profile) => profile.user, { cascade: true })
  profile: UserProfile;
  @OneToMany(() => RefreshToken, (token) => token.user)
  refreshTokens: RefreshToken[];

  @Column({ type: 'boolean', default: false, name: 'is_verified' })
  isVerified: boolean;

  @OneToMany(() => ResetToken, (token) => token.user)
  resetTokens: ResetToken[];

  @OneToMany(() => EmailVerification, (verification) => verification.user)
  emailVerifications: EmailVerification[];
}
