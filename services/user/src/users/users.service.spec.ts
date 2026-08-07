import { Test, TestingModule } from '@nestjs/testing';
import { UsersService } from './users.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import {
  BadRequestException,
  NotFoundException,
  UnauthorizedException,
} from '@nestjs/common';
import { User } from './entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { ResetToken } from './entities/reset-tokens.entity';
import { EmailVerification } from './entities/email-verification.entity';
import { RefreshToken } from './entities/refresh-token.entity';
import { SqsService } from '@ssut/nestjs-sqs';
import { ConfigService } from '@nestjs/config';

const mockSnsSend = jest.fn();

jest.mock('@aws-sdk/client-sns', () => {
  const actual = jest.requireActual('@aws-sdk/client-sns');
  return {
    ...actual,
    SNSClient: jest.fn().mockImplementation(() => ({
      send: mockSnsSend,
    })),
  };
});

describe('UsersService', () => {
  let service: UsersService;

  const mockUserRepository = {
    create: jest.fn(),
    save: jest.fn(),
    findOne: jest.fn(),
    manager: {
      transaction: jest.fn(),
    },
    findAndCount: jest.fn(),
  };
  const mockProfileRepository = {
    create: jest.fn(),
    save: jest.fn(),
    findOne: jest.fn(),
  };
  const mockResetTokenRepository = {
    create: jest.fn(),
    save: jest.fn(),
    findOne: jest.fn(),
  };
  const mockEmailVerificationRepository = {
    create: jest.fn(),
    save: jest.fn(),
    findOne: jest.fn(),
  };
  const mockRefreshTokenRepository = {
    create: jest.fn(),
    save: jest.fn(),
    findOne: jest.fn(),
    update: jest.fn(),
  };
  const mockSqsService = {
    send: jest.fn(),
  };
  const mockConfigService = {
    get: jest.fn().mockImplementation((key: string, defaultValue?: string) => {
      if (key === 'SQS_PRODUCER_NAME') return defaultValue ?? 'user-events';
      if (key === 'SQS_NOTIFICATION_PRODUCER_NAME')
        return defaultValue ?? 'notifications';
      if (key === 'NOTIFICATION_QUEUE_URL')
        return 'http://localhost:4566/000000000000/notification-queue';
      if (key === 'USER_EVENTS_TOPIC_ARN')
        return 'arn:aws:sns:us-east-1:000000000000:user-events';
      return defaultValue;
    }),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UsersService,
        { provide: getRepositoryToken(User), useValue: mockUserRepository },
        {
          provide: getRepositoryToken(UserProfile),
          useValue: mockProfileRepository,
        },
        {
          provide: getRepositoryToken(ResetToken),
          useValue: mockResetTokenRepository,
        },
        {
          provide: getRepositoryToken(RefreshToken),
          useValue: mockRefreshTokenRepository,
        },
        {
          provide: getRepositoryToken(EmailVerification),
          useValue: mockEmailVerificationRepository,
        },
        { provide: SqsService, useValue: mockSqsService },
        { provide: ConfigService, useValue: mockConfigService },
      ],
    }).compile();

    service = module.get<UsersService>(UsersService);
  });

  afterEach(() => {
    jest.clearAllMocks();
    mockSnsSend.mockReset();
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('GOA-085 account deletion and data export', () => {
    const userId = '11111111-1111-4111-8111-111111111111';

    beforeEach(() => {
      jest
        .spyOn(service as any, 'revokeAllAccessTokens')
        .mockResolvedValue(undefined);
    });

    it('DELETE /account with wrong password returns 401', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        id: userId,
        email: 'lina@example.com',
        passwordHash: 'hash',
        deletedAt: null,
      });
      jest.spyOn(require('bcrypt'), 'compare').mockResolvedValue(false);

      await expect(
        service.deleteAccount(userId, userId, 'wrong'),
      ).rejects.toThrow(UnauthorizedException);
    });

    it('DELETE /account sets deletedAt, anonymises email, revokes tokens and publishes AccountDeleted', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        id: userId,
        email: 'lina@example.com',
        passwordHash: 'hash',
        deletedAt: null,
      });
      jest.spyOn(require('bcrypt'), 'compare').mockResolvedValue(true);
      const manager = { update: jest.fn() };
      mockUserRepository.manager.transaction.mockImplementation(async (cb) =>
        cb(manager),
      );
      mockSnsSend.mockResolvedValue({});

      const result = await service.deleteAccount(
        userId,
        userId,
        'correct-password',
      );
      await new Promise(process.nextTick);

      expect(result).toMatchObject({
        success: true,
        deletedAt: expect.any(String),
      });
      expect(manager.update).toHaveBeenCalledWith(User, userId, {
        deletedAt: expect.any(Date),
        email: `deleted_${userId}@deleted.goa`,
      });
      expect(manager.update).toHaveBeenCalledWith(
        RefreshToken,
        { userId },
        { revokedAt: expect.any(Date) },
      );
      expect(mockSnsSend).toHaveBeenCalledTimes(1);
      const command = mockSnsSend.mock.calls[0][0];
      expect(command.input.TopicArn).toBe(
        'arn:aws:sns:us-east-1:000000000000:user-events',
      );
      expect(JSON.parse(command.input.Message)).toMatchObject({
        type: 'account.deleted',
        payload: { userId, deletedAt: expect.any(String) },
      });
    });

    it('GET /data-export returns valid JSON sections', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        id: userId,
        email: 'lina@example.com',
        passwordHash: 'hash',
        deletedAt: null,
        profile: { userId, degreeLevel: 'Bachelor' },
      });

      const exported = await service.exportUserData(userId, userId);

      expect(exported).toMatchObject({
        userId,
        profile: expect.objectContaining({ email: 'lina@example.com' }),
        examHistory: [],
        essays: [],
        speakingSessions: [],
      });
      expect(JSON.parse(JSON.stringify(exported))).toBeTruthy();
      expect((exported.profile as any).passwordHash).toBeUndefined();
    });

    it('deleted user attempts login returns 401', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        id: userId,
        email: 'deleted@example.com',
        passwordHash: 'hash',
        deletedAt: new Date(),
      });

      await expect(
        service.internalLogin({
          email: 'deleted@example.com',
          password: 'Secret123!',
        }),
      ).rejects.toThrow(UnauthorizedException);
    });
  });

  describe('forgotPassword (Security Aspect)', () => {
    it('should silently resolve without saving any token if user does not exist', async () => {
      mockUserRepository.findOne.mockResolvedValue(null);

      await expect(
        service.forgotPassword({ email: 'nonexistent@test.com' }),
      ).resolves.not.toThrow();
      expect(mockResetTokenRepository.create).not.toHaveBeenCalled();
      expect(mockResetTokenRepository.save).not.toHaveBeenCalled();
      // No user → nothing to notify.
      expect(mockSqsService.send).not.toHaveBeenCalled();
    });
  });

  // GOA-083 DoD: forgot-password publishes an SQS event and does NOT send email
  // directly (no SES). The User service no longer imports @aws-sdk/client-ses;
  // this asserts the runtime behaviour that replaced it.
  describe('GOA-083 forgotPassword publishes PasswordResetRequested via SQS', () => {
    const userId = '22222222-2222-4222-8222-222222222222';

    it('saves the reset token and publishes the exact PasswordResetRequested payload to the notifications producer', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        id: userId,
        email: 'sara@example.com',
      });
      mockResetTokenRepository.create.mockImplementation((v) => v);
      mockResetTokenRepository.save.mockResolvedValue(undefined);
      mockSqsService.send.mockResolvedValue([]);

      await service.forgotPassword({ email: 'sara@example.com' });

      // A reset token was persisted.
      expect(mockResetTokenRepository.save).toHaveBeenCalledTimes(1);

      // Exactly one SQS publish, to the notifications producer (not user-events).
      expect(mockSqsService.send).toHaveBeenCalledTimes(1);
      const [producerName, message] = mockSqsService.send.mock.calls[0];
      expect(producerName).toBe('notifications');

      // Exact contract: { type, userId, resetToken, email, expiresAt }
      expect(message.body).toEqual({
        type: 'PasswordResetRequested',
        userId,
        resetToken: expect.any(String),
        email: 'sara@example.com',
        expiresAt: expect.any(String),
      });
      // expiresAt is a valid ISO 8601 string.
      expect(() =>
        new Date(message.body.expiresAt).toISOString(),
      ).not.toThrow();
      // The published token is the RAW token (64 hex chars), never the hash form used in DB lookups.
      expect(message.body.resetToken).toMatch(/^[0-9a-f]{64}$/i);
    });

    it('does not send email via any SES path — the only dispatch is the SQS publish', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        id: userId,
        email: 'sara@example.com',
      });
      mockResetTokenRepository.create.mockImplementation((v) => v);
      mockResetTokenRepository.save.mockResolvedValue(undefined);
      mockSqsService.send.mockResolvedValue([]);

      // The service instance exposes no SES client/method — email is delegated
      // entirely to the Notification service. Guard against a regression that
      // reintroduces a direct sender.
      expect((service as any).sesClient).toBeUndefined();
      expect((service as any).sendEmail).toBeUndefined();
      expect((service as any).mailerService).toBeUndefined();

      await service.forgotPassword({ email: 'sara@example.com' });

      expect(mockSqsService.send).toHaveBeenCalledTimes(1);
    });

    it('still returns 200-equivalent (resolves) even when the SQS publish fails', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        id: userId,
        email: 'sara@example.com',
      });
      mockResetTokenRepository.create.mockImplementation((v) => v);
      mockResetTokenRepository.save.mockResolvedValue(undefined);
      mockSqsService.send.mockRejectedValue(new Error('SQS unavailable'));
      jest.spyOn((service as any).logger, 'error').mockImplementation(() => {});

      await expect(
        service.forgotPassword({ email: 'sara@example.com' }),
      ).resolves.toBeUndefined();
    });
  });

  // GOA-083 DoD: registration publishes an SQS event and does NOT send email
  // directly (no SES).
  describe('GOA-083 register publishes EmailVerificationRequired via SQS', () => {
    const newUserId = '33333333-3333-4333-8333-333333333333';

    beforeEach(() => {
      // No existing user with this email.
      mockUserRepository.findOne.mockResolvedValue(null);
      jest.spyOn(require('bcrypt'), 'hash').mockResolvedValue('hashed-pw');
      mockUserRepository.create.mockImplementation((v) => v);
      mockProfileRepository.create.mockImplementation((v) => v);
      mockEmailVerificationRepository.create.mockImplementation((v) => v);

      // Emulate the transaction: the callback saves user, profile and the
      // verification token; the raw token is stamped onto the returned user.
      mockUserRepository.manager.transaction.mockImplementation(async (cb) => {
        const manager = {
          save: jest.fn().mockImplementation(async (_entity, obj) => {
            if (obj && obj.email) {
              obj.id = newUserId;
            }
            return obj;
          }),
        };
        return cb(manager);
      });
    });

    it('publishes the exact EmailVerificationRequired payload to the notifications producer and omits password fields from the response', async () => {
      mockSqsService.send.mockResolvedValue([]);

      const result = await service.register({
        email: 'newuser@example.com',
        password: 'StrongPass123!',
      });

      // Exactly one SQS publish, to the notifications producer.
      expect(mockSqsService.send).toHaveBeenCalledTimes(1);
      const [producerName, message] = mockSqsService.send.mock.calls[0];
      expect(producerName).toBe('notifications');

      // Exact contract: { type, userId, verificationToken, email }
      expect(message.body).toEqual({
        type: 'EmailVerificationRequired',
        userId: newUserId,
        verificationToken: expect.any(String),
        email: 'newuser@example.com',
      });
      expect(message.body.verificationToken).toMatch(/^[0-9a-f]{64}$/i);

      // Response never leaks password or the transient raw token.
      expect((result as any).passwordHash).toBeUndefined();
      expect((result as any).rawVerificationToken).toBeUndefined();
    });

    it('does not send email via any SES path — the only dispatch is the SQS publish', async () => {
      mockSqsService.send.mockResolvedValue([]);

      expect((service as any).sesClient).toBeUndefined();
      expect((service as any).sendEmail).toBeUndefined();
      expect((service as any).mailerService).toBeUndefined();

      await service.register({
        email: 'newuser@example.com',
        password: 'StrongPass123!',
      });

      expect(mockSqsService.send).toHaveBeenCalledTimes(1);
    });

    it('still returns the created user even when the SQS publish fails', async () => {
      mockSqsService.send.mockRejectedValue(new Error('SQS unavailable'));
      jest.spyOn((service as any).logger, 'error').mockImplementation(() => {});

      const result = await service.register({
        email: 'newuser@example.com',
        password: 'StrongPass123!',
      });

      expect((result as any).email).toBe('newuser@example.com');
    });
  });

  describe('findSubscription', () => {
    it('returns only the subscription tier for a known user', async () => {
      mockUserRepository.findOne.mockResolvedValue({
        subscriptionTier: 'paid',
      });

      await expect(service.findSubscription('user-123')).resolves.toEqual({
        subscriptionTier: 'paid',
      });
      expect(mockUserRepository.findOne).toHaveBeenCalledWith({
        where: { id: 'user-123' },
        select: { subscriptionTier: true },
      });
    });

    it('throws NotFoundException for an unknown user', async () => {
      mockUserRepository.findOne.mockResolvedValue(null);

      await expect(service.findSubscription('missing-user')).rejects.toThrow(
        NotFoundException,
      );
    });
  });

  describe('resetPassword (DoD Constraints)', () => {
    it('should throw a 400 BadRequestException if the reset token has expired', async () => {
      const anHourAgo = new Date();
      anHourAgo.setHours(anHourAgo.getHours() - 2); // Expiry passed

      mockResetTokenRepository.findOne.mockResolvedValue({
        id: 'token-uuid',
        userId: 'user-uuid',
        expiresAt: anHourAgo,
        usedAt: null,
      });

      await expect(
        service.resetPassword({
          token: 'raw_token',
          newPassword: 'NewPassword123!',
        }),
      ).rejects.toThrow(BadRequestException);
    });

    it('should throw a 400 BadRequestException if the reset token has already been used', async () => {
      const futureExpiry = new Date();
      futureExpiry.setHours(futureExpiry.getHours() + 1);

      mockResetTokenRepository.findOne.mockResolvedValue({
        id: 'token-uuid',
        userId: 'user-uuid',
        expiresAt: futureExpiry,
        usedAt: new Date(), // Already utilized
      });

      await expect(
        service.resetPassword({
          token: 'raw_token',
          newPassword: 'NewPassword123!',
        }),
      ).rejects.toThrow(BadRequestException);
    });

    it('should revoke every refresh token for the user when the reset succeeds', async () => {
      const futureExpiry = new Date();
      futureExpiry.setHours(futureExpiry.getHours() + 1);
      const userId = 'user-uuid';

      mockResetTokenRepository.findOne.mockResolvedValue({
        id: 'token-uuid',
        userId,
        expiresAt: futureExpiry,
        usedAt: null,
      });

      const transactionalEntityManager = { update: jest.fn() };
      mockUserRepository.manager.transaction.mockImplementation(
        async (cb: (m: typeof transactionalEntityManager) => Promise<void>) =>
          cb(transactionalEntityManager),
      );

      await service.resetPassword({
        token: 'raw_token',
        newPassword: 'NewPassword123!',
      });

      expect(transactionalEntityManager.update).toHaveBeenCalledWith(
        RefreshToken,
        { userId },
        { revokedAt: expect.any(Date) },
      );
    });
  });

  describe('updateProfile (GOA-016)', () => {
    const userId = 'user-uuid-123';
    const dto = { degreeLevel: 'MSc' };
    const mockProfile = { userId, degreeLevel: 'BSc' };
    const mockUser = {
      id: userId,
      email: 'user@example.com',
      subscriptionTier: 'free' as const,
    };

    it('should save the profile and return it successfully', async () => {
      mockProfileRepository.findOne.mockResolvedValue({ ...mockProfile });
      mockProfileRepository.save.mockResolvedValue({ ...mockProfile, ...dto });
      // SNS publish runs async - resolve but do not block
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSnsSend.mockResolvedValue({});

      const result = await service.updateProfile(userId, dto);

      expect(result).toMatchObject({ userId, degreeLevel: 'MSc' });
      expect(mockProfileRepository.save).toHaveBeenCalledTimes(1);
    });

    it('should publish UserUpdated to SNS after a successful profile save', async () => {
      mockProfileRepository.findOne.mockResolvedValue({ ...mockProfile });
      mockProfileRepository.save.mockResolvedValue({ ...mockProfile, ...dto });
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSnsSend.mockResolvedValue({});

      await service.updateProfile(userId, dto);

      // Allow the fire-and-forget microtask to flush
      await new Promise(process.nextTick);

      expect(mockSnsSend).toHaveBeenCalledTimes(1);
      const command = mockSnsSend.mock.calls[0][0];
      expect(command.input.TopicArn).toBe(
        'arn:aws:sns:us-east-1:000000000000:user-events',
      );
      expect(command.input.MessageAttributes).toMatchObject({
        eventType: {
          DataType: 'String',
          StringValue: 'user.updated',
        },
      });
      const event = JSON.parse(command.input.Message);
      // Verify the full event envelope — use expect.any(String) for non-deterministic fields
      expect(event).toMatchObject({
        type: 'user.updated',
        version: '1.0',
        timestamp: expect.any(String),
        correlationId: expect.any(String),
        payload: {
          userId,
          email: mockUser.email,
          subscriptionTier: mockUser.subscriptionTier,
        },
      });
      // correlationId must be a valid UUID v4
      expect(event.correlationId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      );
      // timestamp must be a valid ISO 8601 string
      expect(() => new Date(event.timestamp).toISOString()).not.toThrow();
    });

    it('should still return the saved profile even if SNS publish throws', async () => {
      mockProfileRepository.findOne.mockResolvedValue({ ...mockProfile });
      mockProfileRepository.save.mockResolvedValue({ ...mockProfile, ...dto });
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSnsSend.mockRejectedValue(new Error('SNS unavailable'));

      // Silence the logger so the caught error does not leak to stderr and cause exit code 1
      jest.spyOn((service as any).logger, 'error').mockImplementation(() => {});

      // Should resolve successfully — SNS failure must not propagate
      await expect(
        service.updateProfile(userId, dto as any),
      ).resolves.toMatchObject({ degreeLevel: 'MSc' });

      // Flush the fire-and-forget so the spy handles the rejection before the test tears down
      await new Promise(process.nextTick);

      // The DB save must have occurred regardless of SNS outcome
      expect(mockProfileRepository.save).toHaveBeenCalledTimes(1);
    });

    it('should log an error (not rethrow) when SNS publish fails', async () => {
      mockProfileRepository.findOne.mockResolvedValue({ ...mockProfile });
      mockProfileRepository.save.mockResolvedValue({ ...mockProfile, ...dto });
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSnsSend.mockRejectedValue(new Error('SNS timeout'));

      const loggerErrorSpy = jest
        .spyOn((service as any).logger, 'error')
        .mockImplementation(() => {});

      await service.updateProfile(userId, dto);

      // Flush fire-and-forget
      await new Promise(process.nextTick);

      expect(loggerErrorSpy).toHaveBeenCalledTimes(1);
      expect(loggerErrorSpy.mock.calls[0][0]).toContain(
        `Failed to publish UserUpdated event for user ${userId}`,
      );
    });

    it('should throw NotFoundException when profile does not exist', async () => {
      mockProfileRepository.findOne.mockResolvedValue(null);

      await expect(
        service.updateProfile('nonexistent-id', dto as any),
      ).rejects.toThrow('Profile for user nonexistent-id not found');

      // No user-event publish attempt if profile was not found
      await new Promise(process.nextTick);
      expect(mockSnsSend).not.toHaveBeenCalled();
    });
  });
});
