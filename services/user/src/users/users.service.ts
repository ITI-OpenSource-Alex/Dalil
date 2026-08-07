import {
  Injectable,
  ConflictException,
  NotFoundException,
  BadRequestException,
  UnauthorizedException,
  ForbiddenException,
  Logger,
} from '@nestjs/common';
import {
  InternalLoginDto,
  InternalRefreshDto,
  InternalRevokeDto,
} from './dto/refresh-token.dto';
import Redis from 'ioredis';
import { RefreshToken } from './entities/refresh-token.entity';
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
import { PublishCommand, SNSClient } from '@aws-sdk/client-sns';
import { SqsService } from '@ssut/nestjs-sqs';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class UsersService {
  private readonly logger = new Logger(UsersService.name);

  constructor(
    @InjectRepository(User) private readonly userRepository: Repository<User>,
    @InjectRepository(UserProfile)
    private readonly profileRepository: Repository<UserProfile>,
    @InjectRepository(ResetToken)
    private readonly resetTokenRepository: Repository<ResetToken>,
    @InjectRepository(EmailVerification)
    private readonly emailVerificationRepository: Repository<EmailVerification>,
    @InjectRepository(RefreshToken)
    private readonly refreshTokenRepository: Repository<RefreshToken>,
    private readonly sqsService: SqsService,
    private readonly configService: ConfigService,
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

    // 4. Fire notifications safely outside the database transaction locks.
    //
    // GOA-083: the User service no longer sends verification email directly.
    // It publishes an EmailVerificationRequired event to the notification
    // queue; the Notification service renders the template and sends via SES.
    // A publish failure must not fail registration — the account and token are
    // already committed — so this is fire-and-forget with internal error
    // logging, matching publishUserUpdatedEvent/publishAccountDeletedEvent.
    const rawToken = (savedUser as any).rawVerificationToken;

    await this.publishEmailVerificationRequired({
      userId: savedUser.id,
      verificationToken: rawToken,
      email: savedUser.email,
    });

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

  async findSubscription(
    id: string,
  ): Promise<{ subscriptionTier: 'free' | 'paid' }> {
    const user = await this.userRepository.findOne({
      where: { id },
      select: {
        subscriptionTier: true,
      },
    });

    if (!user) {
      throw new NotFoundException(`User with ID ${id} not found`);
    }

    return { subscriptionTier: user.subscriptionTier };
  }

  async updateProfile(id: string, dto: UpdateProfileDto): Promise<UserProfile> {
    const profile = await this.profileRepository.findOne({
      where: { userId: id },
    });

    if (!profile) {
      throw new NotFoundException(`Profile for user ${id} not found`);
    }

    Object.assign(profile, dto);
    const savedProfile = await this.profileRepository.save(profile);

    // Fire-and-forget: publish UserUpdated to the user-events SNS topic.
    // A failure here must never fail the HTTP request — the DB write is the source of truth.
    void this.publishUserUpdatedEvent(id);

    return savedProfile;
  }

  async deleteAccount(
    userId: string,
    requesterId: string | undefined,
    confirmPassword: string,
  ): Promise<{ success: true; deletedAt: string }> {
    this.assertSelf(userId, requesterId);

    const user = await this.userRepository.findOne({ where: { id: userId } });
    if (!user || user.deletedAt) {
      throw new NotFoundException(`User with ID ${userId} not found`);
    }

    if (!(await bcrypt.compare(confirmPassword, user.passwordHash))) {
      throw new UnauthorizedException('Invalid credentials');
    }

    const deletedAt = new Date();
    const anonymizedEmail = `deleted_${user.id}@deleted.goa`;

    await this.userRepository.manager.transaction(async (manager) => {
      await manager.update(User, user.id, {
        deletedAt,
        email: anonymizedEmail,
      });
      await manager.update(
        RefreshToken,
        { userId: user.id },
        { revokedAt: deletedAt },
      );
    });

    await this.revokeAllAccessTokens(user.id, deletedAt);
    void this.publishAccountDeletedEvent(user.id, deletedAt);

    return { success: true, deletedAt: deletedAt.toISOString() };
  }

  async exportUserData(userId: string, requesterId?: string) {
    this.assertSelf(userId, requesterId);

    const user = await this.userRepository.findOne({
      where: { id: userId },
      relations: { profile: true },
    });
    if (!user || user.deletedAt) {
      throw new NotFoundException(`User with ID ${userId} not found`);
    }

    const { passwordHash: _, ...profile } = user as any;

    const [examHistory, essays, speakingSessions] = await Promise.all([
      this.fetchJsonSection(
        'EXAM_SERVICE_URL',
        `/users/${userId}/exam-history`,
      ),
      this.fetchJsonSection(
        'WRITING_SERVICE_URL',
        `/internal/users/${userId}/essays`,
      ),
      this.fetchJsonSection(
        'SPEAKING_SERVICE_URL',
        `/sessions?userId=${userId}`,
      ),
    ]);

    return {
      exportedAt: new Date().toISOString(),
      userId,
      profile,
      examHistory:
        examHistory?.items ?? examHistory?.results ?? examHistory ?? [],
      essays: essays?.essays ?? essays ?? [],
      speakingSessions: speakingSessions?.sessions ?? speakingSessions ?? [],
    };
  }

  private assertSelf(userId: string, requesterId?: string): void {
    if (!requesterId || requesterId !== userId) {
      throw new ForbiddenException(
        'Users can only access their own account data',
      );
    }
  }

  private async fetchJsonSection(
    configKey: string,
    path: string,
  ): Promise<any> {
    const baseUrl = this.configService.get<string>(configKey);
    if (!baseUrl) {
      return [];
    }
    try {
      const response = await fetch(`${baseUrl}${path}`, {
        headers: {
          'X-Internal-API-Key':
            this.configService.get<string>('INTERNAL_API_KEY', '') || '',
        },
      });
      if (!response.ok) {
        this.logger.warn(
          `Data export section ${configKey} returned ${response.status}`,
        );
        return [];
      }
      return await response.json();
    } catch (error) {
      this.logger.warn(
        `Data export section ${configKey} unavailable`,
        error instanceof Error ? error.message : String(error),
      );
      return [];
    }
  }

  private async publishUserUpdatedEvent(userId: string): Promise<void> {
    try {
      const user = await this.userRepository.findOne({
        where: { id: userId },
        relations: { profile: true },
      });
      if (!user) {
        this.logger.warn(
          `publishUserUpdatedEvent: user ${userId} not found, skipping SQS publish`,
        );
        return;
      }

      const event = {
        type: 'user.updated',
        version: '1.0',
        timestamp: new Date().toISOString(),
        correlationId: crypto.randomUUID(),
        payload: {
          userId: user.id,
          email: user.email,
          subscriptionTier: user.subscriptionTier,

          ects: user.profile?.ects || 0,
          gpa: user.profile?.gpa || 0,
          gpaScale: user.profile?.gpaScale || '4.0',
          ieltsScore: user.profile?.ieltsScore || 0,
          degreeLevel: user.profile?.degreeLevel || 'Bachelor',
          workExperienceYears: user.profile?.workExperienceYears || 0,
          extracurricularsScore: user.profile?.extracurricularsScore || 0,
          targetCountries: user.profile?.targetCountries || [],
        },
      };

      await this.publishUserEvent(event);

      this.logger.log(`UserUpdated event published for user ${userId}`);
    } catch (error) {
      this.logger.error(
        `Failed to publish UserUpdated event for user ${userId}`,
        error instanceof Error ? error.stack : String(error),
      );
    }
  }

  private async publishAccountDeletedEvent(
    userId: string,
    deletedAt: Date,
  ): Promise<void> {
    try {
      const event = {
        type: 'account.deleted',
        version: '1.0',
        timestamp: new Date().toISOString(),
        correlationId: crypto.randomUUID(),
        payload: {
          userId,
          deletedAt: deletedAt.toISOString(),
        },
      };

      await this.publishUserEvent(event);

      this.logger.log(`AccountDeleted event published for user ${userId}`);
    } catch (error) {
      this.logger.error(
        `Failed to publish AccountDeleted event for user ${userId}`,
        error instanceof Error ? error.stack : String(error),
      );
    }
  }

  /**
   * GOA-083: publish an EmailVerificationRequired event to the notification
   * queue so the Notification Lambda renders and sends the verification
   * email. Fire-and-forget — a publish failure must never fail registration.
   */
  private async publishEmailVerificationRequired(params: {
    userId: string;
    verificationToken: string;
    email: string;
  }): Promise<void> {
    try {
      const producerName = this.configService.get<string>(
        'SQS_NOTIFICATION_PRODUCER_NAME',
        'notifications',
      );
      const queueUrl = this.configService.get<string>('NOTIFICATION_QUEUE_URL');
      if (!queueUrl) {
        this.logger.warn(
          'NOTIFICATION_QUEUE_URL is not set — cannot publish EmailVerificationRequired; verification email will not be sent',
        );
        return;
      }

      const event = {
        type: 'EmailVerificationRequired' as const,
        userId: params.userId,
        verificationToken: params.verificationToken,
        email: params.email,
      };

      await this.sqsService.send(producerName, {
        id: crypto.randomUUID(),
        body: event,
      });

      this.logger.log(
        `EmailVerificationRequired event published for user ${params.userId}`,
      );
    } catch (error) {
      this.logger.error(
        `Failed to publish EmailVerificationRequired event for user ${params.userId}`,
        error instanceof Error ? error.stack : String(error),
      );
    }
  }

  /**
   * GOA-083: publish a PasswordResetRequested event to the notification
   * queue so the Notification Lambda renders and sends the reset email.
   * Fire-and-forget — the endpoint always returns a uniform 200 to prevent
   * user enumeration, so a queue failure must not surface to the caller.
   */
  private async publishPasswordResetRequested(params: {
    userId: string;
    resetToken: string;
    email: string;
    expiresAt: string;
  }): Promise<void> {
    try {
      const producerName = this.configService.get<string>(
        'SQS_NOTIFICATION_PRODUCER_NAME',
        'notifications',
      );
      const queueUrl = this.configService.get<string>('NOTIFICATION_QUEUE_URL');
      if (!queueUrl) {
        this.logger.warn(
          'NOTIFICATION_QUEUE_URL is not set — cannot publish PasswordResetRequested; reset email will not be sent',
        );
        return;
      }

      const event = {
        type: 'PasswordResetRequested' as const,
        userId: params.userId,
        resetToken: params.resetToken,
        email: params.email,
        expiresAt: params.expiresAt,
      };

      await this.sqsService.send(producerName, {
        id: crypto.randomUUID(),
        body: event,
      });

      this.logger.log(
        `PasswordResetRequested event published for user ${params.userId}`,
      );
    } catch (error) {
      this.logger.error(
        `Failed to publish PasswordResetRequested event for user ${params.userId}`,
        error instanceof Error ? error.stack : String(error),
      );
    }
  }

  private async publishUserEvent(event: {
    type: string;
    correlationId: string;
    [key: string]: unknown;
  }): Promise<void> {
    const topicArn = this.configService.get<string>('USER_EVENTS_TOPIC_ARN');
    if (!topicArn) {
      throw new Error('USER_EVENTS_TOPIC_ARN environment variable is required');
    }

    const endpoint = this.configService.get<string>('AWS_ENDPOINT');
    const accessKeyId = this.configService.get<string>('AWS_ACCESS_KEY_ID');
    const secretAccessKey = this.configService.get<string>(
      'AWS_SECRET_ACCESS_KEY',
    );
    const snsClient = new SNSClient({
      region: this.configService.get<string>('AWS_REGION', 'us-east-1'),
      ...(endpoint && { endpoint }),
      ...(accessKeyId &&
        secretAccessKey && {
          credentials: { accessKeyId, secretAccessKey },
        }),
    });

    await snsClient.send(
      new PublishCommand({
        TopicArn: topicArn,
        Message: JSON.stringify(event),
        MessageAttributes: {
          eventType: {
            DataType: 'String',
            StringValue: event.type,
          },
        },
      }),
    );
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

    // 6. GOA-083: publish a PasswordResetRequested event instead of sending
    // email directly. The Notification service renders the reset template and
    // sends via SES. Publish failure is logged, not thrown — the endpoint
    // always returns a uniform 200 to prevent user enumeration (see
    // AuthController.forgotPassword), so it must not surface a mail/queue error.
    await this.publishPasswordResetRequested({
      userId: user.id,
      resetToken: rawToken,
      email,
      expiresAt: expiresAt.toISOString(),
    });
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

        // 6. Revoke every refresh token for this user so a leaked/stolen
        // session cannot survive a password reset.
        await transactionalEntityManager.update(
          RefreshToken,
          { userId: tokenRecord.userId },
          { revokedAt: now },
        );
      },
    );

    // 7. Revoking refresh tokens alone did not achieve step 6's stated intent: a
    // stolen ACCESS token kept working for the rest of its hour, and a password
    // reset is exactly what a user does when they believe one was stolen
    // (BUG-028). The gateway checks this per-user epoch on every authenticated
    // request, so stamping it here invalidates all outstanding access tokens.
    await this.revokeAllAccessTokens(tokenRecord.userId, now);
  }

  /**
   * Stamps the revocation epoch read by the gateway's JWT middleware.
   *
   * Key and value format must match `middleware.UserRevokedBeforeKey` in the Go
   * gateway exactly: `user_revoked_before:{userId}` holding unix seconds, with a
   * TTL equal to the access-token lifetime — past that, every token issued
   * before the stamp has expired on its own and the key carries no meaning.
   *
   * Failure is logged rather than thrown: the password is already changed and
   * the refresh tokens already revoked, so raising here would tell the user the
   * reset failed when it succeeded.
   */
  private async revokeAllAccessTokens(userId: string, at: Date): Promise<void> {
    const ACCESS_TOKEN_TTL_SECONDS = 3600;
    const redis = new Redis({
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT || '6379', 10),
    });
    try {
      await redis.set(
        `user_revoked_before:${userId}`,
        Math.floor(at.getTime() / 1000).toString(),
        'EX',
        ACCESS_TOKEN_TTL_SECONDS,
      );
    } catch (error) {
      this.logger.error(
        `Failed to stamp access-token revocation epoch for user ${userId}; ` +
          'outstanding access tokens remain valid until they expire',
        error instanceof Error ? error.stack : String(error),
      );
    } finally {
      redis.disconnect();
    }
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

  async revokeAllForUser(userId: string): Promise<void> {
    await this.refreshTokenRepository.update(
      { userId },
      { revokedAt: new Date() },
    );
  }

  async internalLogin(dto: InternalLoginDto) {
    const user = await this.userRepository.findOne({
      where: { email: dto.email },
    });

    if (
      !user ||
      user.deletedAt ||
      !(await bcrypt.compare(dto.password, user.passwordHash))
    ) {
      throw new UnauthorizedException('Invalid credentials');
    }

    const rawToken = crypto.randomBytes(32).toString('hex');
    const tokenHash = await bcrypt.hash(rawToken, 10);

    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + 30);

    const tokenEntity = this.refreshTokenRepository.create({
      tokenHash,
      userId: user.id,
      expiresAt,
      deviceHint: dto.deviceHint,
    });

    const savedToken = await this.refreshTokenRepository.save(tokenEntity);

    return {
      userId: user.id,
      email: user.email,
      tokenId: savedToken.id,
      rawToken,
      expiresAt: savedToken.expiresAt.toISOString(),
    };
  }

  async internalRefresh(dto: InternalRefreshDto) {
    const token = await this.refreshTokenRepository.findOne({
      where: { id: dto.tokenId },
      relations: { user: true },
    });

    if (!token || !(await bcrypt.compare(dto.rawToken, token.tokenHash))) {
      throw new UnauthorizedException('Invalid refresh token');
    }

    if (token.revokedAt) {
      // If token is already revoked, this is a replay attack! Revoke ALL sessions.
      await this.revokeAllForUser(token.userId);
      throw new ForbiddenException(
        'Replay attack detected. All sessions revoked.',
      );
    }

    if (new Date() > token.expiresAt) {
      throw new UnauthorizedException('Refresh token expired');
    }

    token.revokedAt = new Date();
    const newRawToken = crypto.randomBytes(32).toString('hex');
    const newTokenHash = await bcrypt.hash(newRawToken, 10);
    const newExpiresAt = new Date();
    newExpiresAt.setDate(newExpiresAt.getDate() + 30);

    const newTokenEntity = this.refreshTokenRepository.create({
      tokenHash: newTokenHash,
      userId: token.userId,
      expiresAt: newExpiresAt,
      deviceHint: dto.deviceHint || token.deviceHint, // carry over hint if not provided
    });

    //Atomically save the invalidation and the new token
    await this.refreshTokenRepository.manager.transaction(async (manager) => {
      await manager.save(token);
      await manager.save(newTokenEntity);
    });

    return {
      userId: token.userId,
      email: token.user.email,
      newTokenId: newTokenEntity.id,
      newRawToken,
      expiresAt: newTokenEntity.expiresAt.toISOString(),
    };
  }

  async internalRevoke(dto: InternalRevokeDto) {
    if (dto.revokeAll) {
      await this.revokeAllForUser(dto.userId);
    } else if (dto.tokenId) {
      await this.refreshTokenRepository.update(
        { id: dto.tokenId, userId: dto.userId },
        { revokedAt: new Date() },
      );
    }
  }

  async findAllPaginated(page: number, limit: number) {
    const skip = (page - 1) * limit;
    const [users, total] = await this.userRepository.findAndCount({
      relations: { profile: true },
      skip,
      take: limit,
      order: { createdAt: 'ASC' },
    });
    const mappedUsers = users.map((u) => ({
      userId: u.id,
      email: u.email,
      ects: u.profile?.ects || 0,
      gpa: u.profile?.gpa || 0,
      gpaScale: u.profile?.gpaScale || '4.0',
      ieltsScore: u.profile?.ieltsScore || 0,
      degreeLevel: u.profile?.degreeLevel || 'Bachelor',
      workExperienceYears: u.profile?.workExperienceYears || 0,
      extracurricularsScore: u.profile?.extracurricularsScore || 0,
      targetCountries: u.profile?.targetCountries || [],
    }));
    return {
      users: mappedUsers,
      hasMore: skip + users.length < total,
    };
  }
}
