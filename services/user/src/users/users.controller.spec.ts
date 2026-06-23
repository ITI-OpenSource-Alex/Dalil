import { Test, TestingModule } from '@nestjs/testing';
import { UsersController } from './users.controller';
import { UsersService } from './users.service';
import { ConflictException } from '@nestjs/common';

describe('UsersController', () => {
  let controller: UsersController;
  let service: UsersService;

  const mockUsersService = {
    register: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [UsersController],
      providers: [{ provide: UsersService, useValue: mockUsersService }],
    }).compile();

    controller = module.get<UsersController>(UsersController);
    service = module.get<UsersService>(UsersService);
  });

  it('should throw a 409 ConflictException when email is a duplicate', async () => {
    mockUsersService.register.mockRejectedValue(
      new ConflictException('Email address already registered'),
    );

    const dto = { email: 'duplicate@test.com', password: 'password123' };
    await expect(controller.register(dto)).rejects.toThrow(ConflictException);
  });
});
