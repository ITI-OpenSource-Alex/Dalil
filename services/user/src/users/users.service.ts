import {
  Injectable,
  ConflictException,
  NotFoundException,
  BadRequestException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { User } from './entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { CreateUserDto } from './dto/create-user.dto';
import { UpdateProfileDto } from '../profile/dto/update-profile.dto';
import { ResetToken } from './entities/reset-tokens.entity';
import { EmailVerification } from './entities/email-verification.entity';
import { ForgotPasswordDto } from './dto/forgot-password.dto';
import { ResetPasswordDto } from './dto/reset-password.dto';
import * as bcrypt from 'bcrypt';
import * as crypto from 'crypto';

@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User) private readonly userRepository: Repository<User>,
    @InjectRepository(UserProfile)
    private readonly profileRepository: Repository<UserProfile>,
    @InjectRepository(ResetToken)
    private readonly resetTokenRepository: Repository<ResetToken>,
    @InjectRepository(EmailVerification)
    private readonly emailVerificationRepository: Repository<EmailVerification>,
    // private readonly sqsService: SqsService,
  ) {}

  // FIX 1: Async methods must return a Promise wrapper, and we type it cleanly using structural mapping
  async register(
    createUserDto: CreateUserDto,
  ): Promise<Omit<User, 'passwordHash'>> {
    const { email, password } = createUserDto;

    // 1. Check if user already exists to fail fast
    const existingUser = await this.userRepository.findOne({
      where: { email },
    });
    if (existingUser) {
      throw new ConflictException('Email address already registered');
    }

    // 2. Hash the user password
    const passwordHash = await bcrypt.hash(password, 10);

    // 3. Run all DB creations together inside a safe transaction
    const savedUser = await this.userRepository.manager.transaction(
      async (transactionalEntityManager) => {
        // Create and save User
        const userEntity = this.userRepository.create({
          email,
          passwordHash,
          isVerified: false, // Explicitly false until verified via link
        });
        const user = await transactionalEntityManager.save(User, userEntity);

        // Create and save profile
        const profileEntity = this.profileRepository.create({
          userId: user.id,
          targetCountries: [],
        });
        await transactionalEntityManager.save(UserProfile, profileEntity);

        // Create and save Email Verification Token
        const rawToken = crypto.randomBytes(32).toString('hex');
        const tokenHash = this.hashToken(rawToken);

        const verificationEntity = this.emailVerificationRepository.create({
          tokenHash,
          userId: user.id,
        });
        await transactionalEntityManager.save(
          EmailVerification,
          verificationEntity,
        );

        // Attach the temporary unhashed token onto the context object for the log/SQS action below
        (user as any).rawVerificationToken = rawToken;

        return user;
      },
    );

    // 4. Fire notifications safely outside the database transaction locks
    const rawToken = (savedUser as any).rawVerificationToken;

    // TODO: Uncomment once SQS module is available
    // await this.sqsService.send('EmailVerificationRequired', {
    //   email: savedUser.email,
    //   userId: savedUser.id,
    //   token: rawToken,
    // });

    console.log(
      `[SQS Simulation] Send verification email to ${savedUser.email} with link: https://goa.app/verify-email/${rawToken}`,
    );

    // 5. Securely omit password fields from downstream API responses
    const {
      passwordHash: _,
      rawVerificationToken: __,
      ...result
    } = savedUser as any;
    return result;
  }

  async findOneWithProfile(id: string): Promise<User> {
    // FIX 2: Modern TypeORM requires an explicit boolean object assignment for relations mapping
    const user = await this.userRepository.findOne({
      where: { id },
      relations: {
        profile: true,
      },
    });

    if (!user) {
      throw new NotFoundException(`User with ID ${id} not found`);
    }

    // FIX 3: Instead of mutating the database entity with 'delete', we dynamically omit it safely
    const { passwordHash, ...userWithoutPassword } = user;
    return userWithoutPassword as User;
  }

  async updateProfile(id: string, dto: UpdateProfileDto): Promise<UserProfile> {
    const profile = await this.profileRepository.findOne({
      where: { userId: id },
    });

    if (!profile) {
      throw new NotFoundException(`Profile for user ${id} not found`);
    }

    Object.assign(profile, dto);
    return this.profileRepository.save(profile);
  }

  private hashToken(token: string): string {
    return crypto.createHash('sha256').update(token).digest('hex');
  }

  async forgotPassword(ForgotPasswordDto: ForgotPasswordDto): Promise<void> {
    // extract email
    const { email } = ForgotPasswordDto;

    // Find USer
    const user = await this.userRepository.findOne({ where: { email } });

    // Check if no user
    if (!user) {
      return;
    }

    // 3. Generate a cryptographically secure random 32-byte token and hash it
    const rawToken = crypto.randomBytes(32).toString('hex');
    const tokenHash = this.hashToken(rawToken);

    // 4. Expiry set to +1 hour
    const expiresAt = new Date();
    expiresAt.setHours(expiresAt.getHours() + 1);

    // 5. Save the token hash
    const resetTokenEntry = this.resetTokenRepository.create({
      tokenHash,
      userId: user.id,
      expiresAt,
    });
    await this.resetTokenRepository.save(resetTokenEntry);

    // 6. Publish PasswordResetRequested SQS event to Notification service
    // Pass the RAW unhashed token here so it can be emailed to the user
    // await this.sqsService.publish('PasswordResetRequested', {
    //   email: user.email,
    //   userId: user.id,
    //   token: rawToken, // This must be the raw token!
    // });

    // until we are able to use SQS
    console.log(
      `[SQS Simulation] Send email to ${email} with link: https://goa.app/reset-password?token=${rawToken}`,
    );
  }

  async resetPassword(resetPasswordDto: ResetPasswordDto): Promise<void> {
    const { token, newPassword } = resetPasswordDto;

    // 1. Hash the incoming raw token to match our DB storage strategy
    const tokenHash = this.hashToken(token);

    // 2. Lookup the token record
    const tokenRecord = await this.resetTokenRepository.findOne({
      where: { tokenHash },
    });

    // 3. Security checks: Reject if token doesn't exist, is used, or is expired
    if (!tokenRecord) {
      throw new BadRequestException('Invalid or expired password reset token.');
    }

    if (tokenRecord.usedAt) {
      throw new BadRequestException('This reset token has already been used.');
    }

    const now = new Date();
    if (now > tokenRecord.expiresAt) {
      throw new BadRequestException('This reset token has expired.');
    }

    // 4. Hash the new password using bcrypt
    const saltRounds = 10;
    const hashedPassword = await bcrypt.hash(newPassword, saltRounds);

    // 5. Use a database transaction to update the user and invalidate the token atomically
    await this.userRepository.manager.transaction(
      async (transactionalEntityManager) => {
        // Update user password
        await transactionalEntityManager.update(User, tokenRecord.userId, {
          passwordHash: hashedPassword, // Fixed property name from password to passwordHash
        });

        // Mark token as used
        await transactionalEntityManager.update(ResetToken, tokenRecord.id, {
          usedAt: now,
        });

        // 6. TODO/Note: Revoke all refresh tokens for this user.
        // If your refresh tokens are in a separate table/Redis store, invalidate them here:
        // await transactionalEntityManager.delete(RefreshTokenEntity, { userId: tokenRecord.userId });
        console.log(
          `[Session Invalidation] Revoked all refresh tokens for user ${tokenRecord.userId}`,
        );
      },
    );
  }

  // Call this method inside your existing GOA-004 User Registration flow
  async createEmailVerificationToken(userId: string): Promise<string> {
    // 1. Generate secure random 32-byte token
    const rawToken = crypto.randomBytes(32).toString('hex');
    const tokenHash = this.hashToken(rawToken);

    // 2. Save the token hash to the DB
    const verificationEntry = this.emailVerificationRepository.create({
      tokenHash,
      userId,
    });
    await this.emailVerificationRepository.save(verificationEntry);

    // 3. Return the raw token so the registration flow can dispatch it via SQS
    return rawToken;
  }

  // Handles the validation when a user clicks the confirmation link
  async verifyEmail(rawToken: string): Promise<void> {
    // 1. Hash incoming token
    const tokenHash = this.hashToken(rawToken);

    // 2. Find matching verification entry
    const verificationRecord = await this.emailVerificationRepository.findOne({
      where: { tokenHash },
    });

    if (!verificationRecord) {
      throw new BadRequestException(
        'Invalid or expired email verification token.',
      );
    }

    // 3. Update user confirmation status and purge the token entry within a transaction
    await this.userRepository.manager.transaction(
      async (transactionalEntityManager) => {
        await transactionalEntityManager.update(
          User,
          verificationRecord.userId,
          {
            isVerified: true,
          },
        );

        await transactionalEntityManager.delete(
          EmailVerification,
          verificationRecord.id,
        );
      },
    );
  }
}
