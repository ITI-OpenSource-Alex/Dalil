import { Test, TestingModule } from '@nestjs/testing';
import { AuthController } from './auth.controller';
import { UsersService } from './users.service';

describe('AuthController', () => {
  let controller: AuthController;
  let service: UsersService;

  const mockUsersService = {
    forgotPassword: jest.fn(),
    resetPassword: jest.fn(),
    verifyEmail: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [AuthController],
      providers: [{ provide: UsersService, useValue: mockUsersService }],
    }).compile();

    controller = module.get<AuthController>(AuthController);
    service = module.get<UsersService>(UsersService);
  });

  afterEach(() => {
    jest.clearAllMocks();
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

  describe('verifyEmail', () => {
    it('should return a success message when the token is valid', async () => {
      mockUsersService.verifyEmail.mockResolvedValue(undefined);

      const result = await controller.verifyEmail('raw_token_string');

      expect(service.verifyEmail).toHaveBeenCalledWith('raw_token_string');
      expect(result).toEqual({
        message:
          'Your email address has been verified successfully. Welcome aboard!',
      });
    });
  });
});
