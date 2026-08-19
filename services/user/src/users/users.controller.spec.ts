import { Test, TestingModule } from '@nestjs/testing';
import { UsersController } from './users.controller';
import { UsersService } from './users.service';
import { ConflictException } from '@nestjs/common';
import { GUARDS_METADATA } from '@nestjs/common/constants';
import { InternalAuthGuard } from '../common/guards/internal-auth.guard';

describe('UsersController', () => {
  let controller: UsersController;
  let service: UsersService;

  const mockUsersService = {
    register: jest.fn(),
    findAllPaginated: jest.fn(),
    findSubscription: jest.fn(),
    updateSubscription: jest.fn(),
    deleteAccount: jest.fn(),
    exportUserData: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [UsersController],
      providers: [{ provide: UsersService, useValue: mockUsersService }],
    }).compile();

    controller = module.get<UsersController>(UsersController);
    service = module.get<UsersService>(UsersService);
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  it('should throw a 409 ConflictException when email is a duplicate', async () => {
    mockUsersService.register.mockRejectedValue(
      new ConflictException('Email address already registered'),
    );

    const dto = { email: 'duplicate@test.com', password: 'password123' };
    await expect(controller.register(dto)).rejects.toThrow(ConflictException);
  });

  describe('findAllPaginated', () => {
    it('should return paginated users with all required scoring fields and hasMore flag', async () => {
      const mockResult = {
        users: [
          {
            id: '1',
            workExperienceYears: 2,
            extracurricularsScore: 85,
            gpaScale: '4.0',
          },
        ],
        hasMore: false,
      };
      mockUsersService.findAllPaginated.mockResolvedValue(mockResult);

      const result = await controller.findAllPaginated('1', '50');

      expect(service.findAllPaginated).toHaveBeenCalledWith(1, 50);
      expect(result).toEqual(mockResult);
      // Assert explicitly that the payload includes the critical fields
      expect(result.users[0]).toHaveProperty('workExperienceYears');
      expect(result.users[0]).toHaveProperty('extracurricularsScore');
      expect(result.users[0]).toHaveProperty('gpaScale');
    });
  });

  describe('account deletion and data export', () => {
    it('deleteAccount forwards id, requester id and password', async () => {
      mockUsersService.deleteAccount.mockResolvedValue({ success: true });

      await controller.deleteAccount('user-123', { confirmPassword: 'pw' }, 'user-123');

      expect(service.deleteAccount).toHaveBeenCalledWith('user-123', 'user-123', 'pw');
    });

    it('exportData forwards id and requester id', async () => {
      mockUsersService.exportUserData.mockResolvedValue({ userId: 'user-123' });

      await controller.exportData('user-123', 'user-123');

      expect(service.exportUserData).toHaveBeenCalledWith('user-123', 'user-123');
    });
  });

  describe('findSubscription', () => {
    it('returns the narrow service response', async () => {
      mockUsersService.findSubscription.mockResolvedValue({
        subscriptionTier: 'free',
      });

      await expect(controller.findSubscription('user-123')).resolves.toEqual({
        subscriptionTier: 'free',
      });
      expect(service.findSubscription).toHaveBeenCalledWith('user-123');
    });

    it('is protected by InternalAuthGuard', () => {
      const guards = Reflect.getMetadata(
        GUARDS_METADATA,
        controller.findSubscription,
      );

      expect(guards).toContain(InternalAuthGuard);
    });
  });

  // GOA-039
  describe('updateSubscription', () => {
    it('delegates the tier change to the service', async () => {
      mockUsersService.updateSubscription.mockResolvedValue({
        subscriptionTier: 'paid',
      });

      await expect(
        controller.updateSubscription('user-123', { tier: 'paid' }),
      ).resolves.toEqual({ subscriptionTier: 'paid' });

      expect(service.updateSubscription).toHaveBeenCalledWith(
        'user-123',
        'paid',
      );
    });

    it('is protected by InternalAuthGuard', () => {
      // This is the one route in the product that can hand out paid access.
      // A user session must never be sufficient to reach it.
      const guards = Reflect.getMetadata(
        GUARDS_METADATA,
        controller.updateSubscription,
      );

      expect(guards).toContain(InternalAuthGuard);
    });
  });
});

