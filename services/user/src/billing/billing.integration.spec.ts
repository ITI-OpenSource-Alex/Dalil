import { Test, TestingModule } from '@nestjs/testing';
import { HttpStatus, INestApplication, ValidationPipe } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { getRepositoryToken } from '@nestjs/typeorm';
import { SqsService } from '@ssut/nestjs-sqs';
import * as request from 'supertest';
import { BillingController } from './billing.controller';
import { BillingService } from './billing.service';
import { DemoCheckoutStore } from './demo-checkout.store';
import { UsersService } from '../users/users.service';
import { SubscriptionCacheService } from '../common/redis/subscription-cache.service';
import { User } from '../users/entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { ResetToken } from '../users/entities/reset-tokens.entity';
import { EmailVerification } from '../users/entities/email-verification.entity';
import { RefreshToken } from '../users/entities/refresh-token.entity';

/**
 * GOA-039 — the chain the ticket cares about, wired together over real HTTP:
 *
 *   POST /billing/checkout      -> token minted, nothing granted
 *   POST /billing/demo/confirm  -> outcome decided, tier written, cache dropped
 *   POST /billing/cancel        -> tier reverted, cache dropped
 *
 * Only the two edges are mocked: the TypeORM repository (no Postgres) and
 * ioredis (no Redis). Everything between them is the real code path, including
 * the guard, the ValidationPipe and the controller.
 */

const mockRedisDel = jest.fn();
const mockRedisSet = jest.fn();
const mockRedisGetDel = jest.fn();
jest.mock('ioredis', () => ({
  __esModule: true,
  default: jest.fn().mockImplementation(() => ({
    del: mockRedisDel,
    set: mockRedisSet,
    getdel: mockRedisGetDel,
    disconnect: jest.fn(),
  })),
}));

const INTERNAL_KEY = 'internal-key-for-tests';
const SUCCESS_CARD = '4242424242424242';
const DECLINE_CARD = '4000000000009995';
const RETURN_URLS = {
  successUrl: 'http://localhost:3000/billing/success',
  cancelUrl: 'http://localhost:3000/pricing?checkout=cancelled',
};

describe('Billing (integration)', () => {
  let app: INestApplication;
  let stored: { id: string; email: string; subscriptionTier: 'free' | 'paid' };

  const userRepository = {
    findOne: jest.fn(),
    save: jest.fn(),
    create: jest.fn(),
  };
  const noopRepository = () => ({
    findOne: jest.fn(),
    save: jest.fn(),
    create: jest.fn(),
  });

  beforeAll(() => {
    process.env.INTERNAL_API_KEY = INTERNAL_KEY;
  });

  beforeEach(async () => {
    jest.clearAllMocks();
    delete process.env.NODE_ENV;
    mockRedisDel.mockResolvedValue(1);
    mockRedisSet.mockResolvedValue('OK');

    stored = {
      id: 'user-1',
      email: 'student@example.com',
      subscriptionTier: 'free',
    };
    userRepository.findOne.mockImplementation(({ where }) =>
      Promise.resolve(where.id === stored.id ? stored : null),
    );
    userRepository.save.mockImplementation((value) => {
      Object.assign(stored, value);
      return Promise.resolve(stored);
    });

    const moduleFixture: TestingModule = await Test.createTestingModule({
      controllers: [BillingController],
      providers: [
        BillingService,
        DemoCheckoutStore,
        UsersService,
        SubscriptionCacheService,
        { provide: getRepositoryToken(User), useValue: userRepository },
        {
          provide: getRepositoryToken(UserProfile),
          useValue: noopRepository(),
        },
        { provide: getRepositoryToken(ResetToken), useValue: noopRepository() },
        {
          provide: getRepositoryToken(EmailVerification),
          useValue: noopRepository(),
        },
        {
          provide: getRepositoryToken(RefreshToken),
          useValue: noopRepository(),
        },
        { provide: SqsService, useValue: { send: jest.fn() } },
        {
          provide: ConfigService,
          useValue: { get: (key: string) => ({ BILLING_MODE: 'demo' })[key] },
        },
      ],
    }).compile();

    app = moduleFixture.createNestApplication();
    // The same global pipe main.ts installs, so 422s here are real.
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        transform: true,
        errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY,
      }),
    );
    await app.init();
  });

  afterEach(async () => {
    await app.close();
  });

  const internal = (path: string, userId = 'user-1') =>
    request(app.getHttpServer())
      .post(path)
      .set('X-Internal-Api-Key', INTERNAL_KEY)
      .set('X-User-Id', userId);

  /** Opens a checkout and returns the token the store was asked to hold. */
  async function openCheckout(userId = 'user-1'): Promise<string> {
    const response = await internal('/billing/checkout', userId)
      .send(RETURN_URLS)
      .expect(201);
    return response.body.token as string;
  }

  /** Makes the store return a session for `token`, as Redis would. */
  function seedSession(token: string, userId = 'user-1') {
    mockRedisGetDel.mockImplementation((key: string) =>
      key.endsWith(token)
        ? Promise.resolve(
            JSON.stringify({
              userId,
              ...RETURN_URLS,
              createdAt: new Date().toISOString(),
            }),
          )
        : Promise.resolve(null),
    );
  }

  describe('POST /billing/checkout', () => {
    it('mints an opaque token and grants nothing', async () => {
      const token = await openCheckout();

      expect(token).toMatch(/^[a-f0-9]{64}$/);
      expect(stored.subscriptionTier).toBe('free');
      expect(mockRedisSet).toHaveBeenCalled();
    });

    it('refuses a caller without the internal key', async () => {
      await request(app.getHttpServer())
        .post('/billing/checkout')
        .set('X-User-Id', 'user-1')
        .send(RETURN_URLS)
        .expect(401);
    });

    it('refuses a call that names no user', async () => {
      await request(app.getHttpServer())
        .post('/billing/checkout')
        .set('X-Internal-Api-Key', INTERNAL_KEY)
        .send(RETURN_URLS)
        .expect(401);
    });

    it('rejects a malformed return URL with 422', async () => {
      await internal('/billing/checkout')
        .send({ successUrl: 'not-a-url', cancelUrl: 'also-not-a-url' })
        .expect(422);
    });

    it('strips unknown fields, so a client cannot smuggle a tier', async () => {
      await internal('/billing/checkout')
        .send({ ...RETURN_URLS, tier: 'paid', subscriptionTier: 'paid' })
        .expect(201);

      expect(stored.subscriptionTier).toBe('free');
    });

    it('409s for an account that already has the plan', async () => {
      stored.subscriptionTier = 'paid';
      await internal('/billing/checkout').send(RETURN_URLS).expect(409);
    });
  });

  describe('POST /billing/demo/confirm', () => {
    it('upgrades the user, persists the tier and drops the Gateway cache', async () => {
      const token = await openCheckout();
      seedSession(token);

      const response = await internal('/billing/demo/confirm')
        .send({ token, cardNumber: SUCCESS_CARD })
        .expect(200);

      expect(response.body).toEqual({
        status: 'succeeded',
        redirectUrl: RETURN_URLS.successUrl,
      });
      expect(stored.subscriptionTier).toBe('paid');
      // Without this the Gateway serves a cached "free" for up to
      // SUBSCRIPTION_CACHE_TTL and the 5-second criterion is unreachable.
      expect(mockRedisDel).toHaveBeenCalledWith('subtier:v1:user-1');
    });

    it('declines the insufficient-funds card and changes nothing', async () => {
      const token = await openCheckout();
      seedSession(token);

      const response = await internal('/billing/demo/confirm')
        .send({ token, cardNumber: DECLINE_CARD })
        .expect(200);

      expect(response.body.status).toBe('declined');
      expect(stored.subscriptionTier).toBe('free');
      expect(mockRedisDel).not.toHaveBeenCalled();
    });

    it('rejects a spent token, so a replay cannot upgrade twice', async () => {
      const token = await openCheckout();
      seedSession(token);

      await internal('/billing/demo/confirm')
        .send({ token, cardNumber: SUCCESS_CARD })
        .expect(200);

      // GETDEL means the second read finds nothing.
      mockRedisGetDel.mockResolvedValue(null);
      await internal('/billing/demo/confirm')
        .send({ token, cardNumber: SUCCESS_CARD })
        .expect(400);

      expect(stored.subscriptionTier).toBe('paid');
    });

    it('refuses a token minted for a different user', async () => {
      const token = await openCheckout();
      seedSession(token, 'victim-user');

      await internal('/billing/demo/confirm', 'attacker-user')
        .send({ token, cardNumber: SUCCESS_CARD })
        .expect(400);

      expect(stored.subscriptionTier).toBe('free');
    });

    it('rejects a token that is not a checkout token at all', async () => {
      await internal('/billing/demo/confirm')
        .send({ token: 'not-a-token', cardNumber: SUCCESS_CARD })
        .expect(422);
    });

    it('rejects a card field carrying something other than digits', async () => {
      const token = await openCheckout();
      await internal('/billing/demo/confirm')
        .send({ token, cardNumber: "'; DROP TABLE users; --" })
        .expect(422);
    });

    it('requires the internal key', async () => {
      const token = await openCheckout();
      await request(app.getHttpServer())
        .post('/billing/demo/confirm')
        .set('X-User-Id', 'user-1')
        .send({ token, cardNumber: SUCCESS_CARD })
        .expect(401);
    });
  });

  describe('POST /billing/cancel', () => {
    it('downgrades and drops the cache so the gate closes again', async () => {
      stored.subscriptionTier = 'paid';

      const response = await internal('/billing/cancel').send({}).expect(200);

      expect(response.body).toEqual({ subscriptionTier: 'free' });
      expect(stored.subscriptionTier).toBe('free');
      expect(mockRedisDel).toHaveBeenCalledWith('subtier:v1:user-1');
    });

    it('409s for an account that is not on a paid plan', async () => {
      await internal('/billing/cancel').send({}).expect(409);
    });

    it('requires the internal key', async () => {
      stored.subscriptionTier = 'paid';
      await request(app.getHttpServer())
        .post('/billing/cancel')
        .set('X-User-Id', 'user-1')
        .send({})
        .expect(401);

      expect(stored.subscriptionTier).toBe('paid');
    });
  });
});
