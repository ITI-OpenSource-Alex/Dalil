import { Test, TestingModule } from '@nestjs/testing';
import { UsersService } from './users.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import { BadRequestException } from '@nestjs/common';
import { User } from './entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { ResetToken } from './entities/reset-tokens.entity';
import { EmailVerification } from './entities/email-verification.entity';
import { RefreshToken } from './entities/refresh-token.entity';
import { SqsService } from '@ssut/nestjs-sqs';
import { ConfigService } from '@nestjs/config';

describe('UsersService', () => {
  let service: UsersService;

  const mockUserRepository = {
    create: jest.fn(),
    save: jest.fn(),
    findOne: jest.fn(),
    manager: {
      transaction: jest.fn(),
    },
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
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('forgotPassword (Security Aspect)', () => {
    it('should silently resolve without saving any token if user does not exist', async () => {
      mockUserRepository.findOne.mockResolvedValue(null);

      await expect(
        service.forgotPassword({ email: 'nonexistent@test.com' }),
      ).resolves.not.toThrow();
      expect(mockResetTokenRepository.create).not.toHaveBeenCalled();
      expect(mockResetTokenRepository.save).not.toHaveBeenCalled();
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
      // SQS lookup runs async - resolve but do not block
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSqsService.send.mockResolvedValue([]);

      const result = await service.updateProfile(userId, dto as any);

      expect(result).toMatchObject({ userId, degreeLevel: 'MSc' });
      expect(mockProfileRepository.save).toHaveBeenCalledTimes(1);
    });

    it('should call SqsService.send after a successful profile save', async () => {
      mockProfileRepository.findOne.mockResolvedValue({ ...mockProfile });
      mockProfileRepository.save.mockResolvedValue({ ...mockProfile, ...dto });
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSqsService.send.mockResolvedValue([]);

      await service.updateProfile(userId, dto as any);

      // Allow the fire-and-forget microtask to flush
      await new Promise(process.nextTick);

      expect(mockSqsService.send).toHaveBeenCalledTimes(1);
      const [producerName, message] = mockSqsService.send.mock.calls[0];
      expect(producerName).toBe('user-events');
      // Verify the full event envelope — use expect.any(String) for non-deterministic fields
      expect(message.body).toMatchObject({
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
      expect(message.body.correlationId).toMatch(
        /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
      );
      // timestamp must be a valid ISO 8601 string
      expect(() => new Date(message.body.timestamp).toISOString()).not.toThrow();
      // message.id must equal correlationId (our convention)
      expect(message.id).toBe(message.body.correlationId);
    });

    it('should still return the saved profile even if SqsService.send throws', async () => {
      mockProfileRepository.findOne.mockResolvedValue({ ...mockProfile });
      mockProfileRepository.save.mockResolvedValue({ ...mockProfile, ...dto });
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSqsService.send.mockRejectedValue(new Error('SQS unavailable'));

      // Silence the logger so the caught error does not leak to stderr and cause exit code 1
      jest.spyOn((service as any).logger, 'error').mockImplementation(() => { });

      // Should resolve successfully — SQS failure must not propagate
      await expect(
        service.updateProfile(userId, dto as any),
      ).resolves.toMatchObject({ degreeLevel: 'MSc' });

      // Flush the fire-and-forget so the spy handles the rejection before the test tears down
      await new Promise(process.nextTick);

      // The DB save must have occurred regardless of SQS outcome
      expect(mockProfileRepository.save).toHaveBeenCalledTimes(1);
    });

    it('should log an error (not rethrow) when SQS publish fails', async () => {
      mockProfileRepository.findOne.mockResolvedValue({ ...mockProfile });
      mockProfileRepository.save.mockResolvedValue({ ...mockProfile, ...dto });
      mockUserRepository.findOne.mockResolvedValue(mockUser);
      mockSqsService.send.mockRejectedValue(new Error('SQS timeout'));

      const loggerErrorSpy = jest
        .spyOn((service as any).logger, 'error')
        .mockImplementation(() => { });

      await service.updateProfile(userId, dto as any);

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

      // No SQS attempt if profile was not found
      await new Promise(process.nextTick);
      expect(mockSqsService.send).not.toHaveBeenCalled();
    });
  });
});

