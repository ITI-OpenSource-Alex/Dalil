import { Test, TestingModule } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import {
  BadRequestException,
  ConflictException,
  ServiceUnavailableException,
} from '@nestjs/common';
import { BillingService } from './billing.service';
import { DemoCheckoutStore } from './demo-checkout.store';
import { UsersService } from '../users/users.service';

/**
 * GOA-039 demo billing.
 *
 * The security properties under test are the ones that survive the payment
 * being simulated: the token decides whose checkout it is, it is spent exactly
 * once, and the tier is granted by this service and nowhere else.
 */

const SUCCESS_CARD = '4242424242424242';
const DECLINE_CARD = '4000000000009995';

const SESSION = {
  userId: 'user-1',
  successUrl: 'http://localhost:3000/billing/success',
  cancelUrl: 'http://localhost:3000/pricing?checkout=cancelled',
  createdAt: '2026-01-01T00:00:00.000Z',
};

describe('BillingService (demo)', () => {
  let service: BillingService;
  let usersService: { findById: jest.Mock; updateSubscription: jest.Mock };
  let store: { create: jest.Mock; consume: jest.Mock };

  async function build(
    config: Record<string, string> = { BILLING_MODE: 'demo' },
  ) {
    usersService = {
      findById: jest.fn(),
      updateSubscription: jest
        .fn()
        .mockResolvedValue({ subscriptionTier: 'paid' }),
    };
    store = {
      create: jest.fn().mockResolvedValue('a'.repeat(64)),
      consume: jest.fn().mockResolvedValue({ ...SESSION }),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        BillingService,
        { provide: UsersService, useValue: usersService },
        { provide: DemoCheckoutStore, useValue: store },
        {
          provide: ConfigService,
          useValue: { get: (key: string) => config[key] },
        },
      ],
    }).compile();

    service = module.get<BillingService>(BillingService);
  }

  const freeUser = {
    id: 'user-1',
    email: 'student@example.com',
    subscriptionTier: 'free',
  };
  const paidUser = { ...freeUser, subscriptionTier: 'paid' };

  beforeEach(async () => {
    delete process.env.NODE_ENV;
    await build();
  });

  afterEach(() => {
    delete process.env.NODE_ENV;
  });

  describe('createCheckoutSession', () => {
    it('mints a session token for a free user', async () => {
      usersService.findById.mockResolvedValue(freeUser);

      await expect(
        service.createCheckoutSession(
          'user-1',
          SESSION.successUrl,
          SESSION.cancelUrl,
        ),
      ).resolves.toEqual({ token: 'a'.repeat(64) });

      // The return URLs are stored with the session so the confirm step never
      // has to accept one from the browser.
      expect(store.create).toHaveBeenCalledWith(
        'user-1',
        SESSION.successUrl,
        SESSION.cancelUrl,
      );
    });

    it('refuses a second subscription for an already-paid account', async () => {
      usersService.findById.mockResolvedValue(paidUser);

      await expect(
        service.createCheckoutSession(
          'user-1',
          SESSION.successUrl,
          SESSION.cancelUrl,
        ),
      ).rejects.toBeInstanceOf(ConflictException);
      expect(store.create).not.toHaveBeenCalled();
    });

    it('grants nothing on its own', async () => {
      usersService.findById.mockResolvedValue(freeUser);

      await service.createCheckoutSession(
        'user-1',
        SESSION.successUrl,
        SESSION.cancelUrl,
      );

      // Opening a checkout is not paying for one.
      expect(usersService.updateSubscription).not.toHaveBeenCalled();
    });
  });

  describe('confirmPayment', () => {
    it('upgrades the user on the success card', async () => {
      await expect(
        service.confirmPayment('user-1', 'a'.repeat(64), SUCCESS_CARD),
      ).resolves.toEqual({
        status: 'succeeded',
        redirectUrl: SESSION.successUrl,
      });

      expect(usersService.updateSubscription).toHaveBeenCalledWith(
        'user-1',
        'paid',
      );
    });

    it('accepts the success card typed with spaces', async () => {
      const result = await service.confirmPayment(
        'user-1',
        'a'.repeat(64),
        '4242 4242 4242 4242',
      );
      expect(result.status).toBe('succeeded');
    });

    it('declines the insufficient-funds card without upgrading', async () => {
      const result = await service.confirmPayment(
        'user-1',
        'a'.repeat(64),
        DECLINE_CARD,
      );

      expect(result).toEqual({
        status: 'declined',
        message: 'Your card has insufficient funds.',
      });
      expect(usersService.updateSubscription).not.toHaveBeenCalled();
    });

    it('declines any card that is not in the demo table', async () => {
      const result = await service.confirmPayment(
        'user-1',
        'a'.repeat(64),
        '1234567812345678',
      );

      expect(result.status).toBe('declined');
      expect(usersService.updateSubscription).not.toHaveBeenCalled();
    });

    it('rejects a token that has already been spent', async () => {
      // The store consumes atomically, so a second submit sees nothing.
      store.consume.mockResolvedValue(null);

      await expect(
        service.confirmPayment('user-1', 'a'.repeat(64), SUCCESS_CARD),
      ).rejects.toBeInstanceOf(BadRequestException);
      expect(usersService.updateSubscription).not.toHaveBeenCalled();
    });

    it('refuses a token that belongs to a different user', async () => {
      // The decisive test: holding somebody else's checkout token must not
      // upgrade you, and must not upgrade them either.
      store.consume.mockResolvedValue({ ...SESSION, userId: 'victim' });

      await expect(
        service.confirmPayment('attacker', 'a'.repeat(64), SUCCESS_CARD),
      ).rejects.toBeInstanceOf(BadRequestException);
      expect(usersService.updateSubscription).not.toHaveBeenCalled();
    });

    it('upgrades exactly the user the token names, not the one who asked', async () => {
      // Belt and braces on the same property: the tier write uses the caller
      // identity that has already been proven to match the session.
      await service.confirmPayment('user-1', 'a'.repeat(64), SUCCESS_CARD);

      expect(usersService.updateSubscription).toHaveBeenCalledTimes(1);
      expect(usersService.updateSubscription).toHaveBeenCalledWith(
        'user-1',
        'paid',
      );
    });

    it('never logs the card number', async () => {
      const logs: string[] = [];
      jest
        .spyOn(service['logger'], 'log')
        .mockImplementation((message: unknown) => {
          logs.push(String(message));
        });

      await service.confirmPayment('user-1', 'a'.repeat(64), DECLINE_CARD);
      await build();

      for (const line of logs) {
        expect(line).not.toContain(DECLINE_CARD);
        expect(line).not.toContain('4000');
      }
    });
  });

  describe('cancelSubscription', () => {
    it('downgrades a paid user to free', async () => {
      usersService.findById.mockResolvedValue(paidUser);
      usersService.updateSubscription.mockResolvedValue({
        subscriptionTier: 'free',
      });

      await expect(service.cancelSubscription('user-1')).resolves.toEqual({
        subscriptionTier: 'free',
      });
      expect(usersService.updateSubscription).toHaveBeenCalledWith(
        'user-1',
        'free',
      );
    });

    it('refuses to cancel a plan the account does not have', async () => {
      usersService.findById.mockResolvedValue(freeUser);

      await expect(service.cancelSubscription('user-1')).rejects.toBeInstanceOf(
        ConflictException,
      );
      expect(usersService.updateSubscription).not.toHaveBeenCalled();
    });
  });

  describe('safety', () => {
    it('refuses to run at all in production', async () => {
      // Demo billing grants the paid tier without taking money. Whatever the
      // configuration says, it must never answer in a production build.
      process.env.NODE_ENV = 'production';
      await build({ BILLING_MODE: 'demo' });

      expect(service.isEnabled()).toBe(false);
      await expect(
        service.createCheckoutSession(
          'user-1',
          SESSION.successUrl,
          SESSION.cancelUrl,
        ),
      ).rejects.toBeInstanceOf(ServiceUnavailableException);
      await expect(
        service.confirmPayment('user-1', 'a'.repeat(64), SUCCESS_CARD),
      ).rejects.toBeInstanceOf(ServiceUnavailableException);
      await expect(service.cancelSubscription('user-1')).rejects.toBeInstanceOf(
        ServiceUnavailableException,
      );
    });

    it('is disabled when billing mode is anything but demo', async () => {
      await build({ BILLING_MODE: 'off' });

      expect(service.isEnabled()).toBe(false);
      await expect(
        service.confirmPayment('user-1', 'a'.repeat(64), SUCCESS_CARD),
      ).rejects.toBeInstanceOf(ServiceUnavailableException);
    });

    it('defaults to demo when no mode is configured', async () => {
      await build({});
      expect(service.isEnabled()).toBe(true);
    });
  });
});
