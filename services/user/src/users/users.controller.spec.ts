import { Test, TestingModule } from '@nestjs/testing';
import { UsersController } from './users.controller';
import { UsersService } from './users.service';
import { ConflictException } from '@nestjs/common';

describe('UsersController', () => {
  let controller: UsersController;
  let service: UsersService;

  const mockUsersService = {
    register: jest.fn(),
    forgotPassword: jest.fn(),
    resetPassword: jest.fn(),
    verifyEmail: jest.fn(),
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

  describe('forgotPassword', () => {
    it('should return a 200 status and a uniform message to prevent enumeration', async () => {
      mockUsersService.forgotPassword.mockResolvedValue(undefined);

      const dto = { email: 'any-email@test.com' };
      const result = await controller.forgotPassword(dto);

      expect(service.forgotPassword).toHaveBeenCalledWith(dto);
      expect(result).toEqual({
        message:
          'If the email matches an account in our system, a reset link has been sent.',
      });
    });
  });

  describe('resetPassword', () => {
    it('should return a success message when resetting the password succeeds', async () => {
      mockUsersService.resetPassword.mockResolvedValue(undefined);

      const dto = {
        token: 'raw_token_string',
        newPassword: 'NewSecurePassword123!',
      };
      const result = await controller.resetPassword(dto);

      expect(service.resetPassword).toHaveBeenCalledWith(dto);
      expect(result).toEqual({
        message:
          'Password has been successfully reset. You can now log in with your new password.',
      });
    });
  });
});
