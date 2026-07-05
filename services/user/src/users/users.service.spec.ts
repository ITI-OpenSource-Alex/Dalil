import { Test, TestingModule } from '@nestjs/testing';
import { UsersService } from './users.service';
import { getRepositoryToken } from '@nestjs/typeorm';
import { BadRequestException } from '@nestjs/common';
import { User } from './entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { ResetToken } from './entities/reset-tokens.entity';
import { EmailVerification } from './entities/email-verification.entity';
import { RefreshToken } from './entities/refresh-token.entity';
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
});
