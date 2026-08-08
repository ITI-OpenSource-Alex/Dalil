import { Injectable, Logger } from '@nestjs/common';
import Redis from 'ioredis';
import * as crypto from 'crypto';

/**
 * Pending demo checkouts, held in Redis (GOA-039).
 *
 * A checkout session is created when the user clicks Upgrade and consumed when
 * they submit the demo card form. Three properties matter, and Redis gives all
 * three cheaply:
 *
 *   · short-lived   — a 15 minute TTL, so an abandoned checkout cleans itself
 *                     up rather than accumulating rows nothing will ever read.
 *   · single-use    — consumed with GETDEL, which reads and deletes in one
 *                     atomic step. Two tabs submitting the same token cannot
 *                     both succeed.
 *   · server-owned  — the token is minted here and the user it belongs to is
 *                     stored here. The browser holds an opaque string and
 *                     cannot say whose checkout it is.
 *
 * Postgres was the alternative. It would mean an entity, a migration and a
 * sweeper for rows that are meaningless after fifteen minutes; the durable
 * half of this flow (the subscription tier itself) already lives there.
 */

export interface DemoCheckoutSession {
  userId: string;
  successUrl: string;
  cancelUrl: string;
  createdAt: string;
}

const KEY_PREFIX = 'demo_checkout:v1:';
const TTL_SECONDS = 15 * 60;

@Injectable()
export class DemoCheckoutStore {
  private readonly logger = new Logger(DemoCheckoutStore.name);

  private client(): Redis {
    return new Redis({
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT || '6379', 10),
      maxRetriesPerRequest: 1,
    });
  }

  /** Mints a session and returns its opaque token. */
  async create(
    userId: string,
    successUrl: string,
    cancelUrl: string,
  ): Promise<string> {
    // 32 bytes from the CSPRNG. The token is a bearer credential for one
    // upgrade, so it must not be guessable from a user id or a timestamp.
    const token = crypto.randomBytes(32).toString('hex');
    const session: DemoCheckoutSession = {
      userId,
      successUrl,
      cancelUrl,
      createdAt: new Date().toISOString(),
    };

    const redis = this.client();
    try {
      await redis.set(
        KEY_PREFIX + token,
        JSON.stringify(session),
        'EX',
        TTL_SECONDS,
      );
    } finally {
      redis.disconnect();
    }

    return token;
  }

  /**
   * Reads and destroys a session in one atomic operation.
   *
   * Returns null for a token that never existed, has expired, or has already
   * been used -- all three are the same thing to the caller, and saying which
   * would help someone probing for valid tokens.
   */
  async consume(token: string): Promise<DemoCheckoutSession | null> {
    const redis = this.client();
    try {
      const raw = await redis.getdel(KEY_PREFIX + token);
      if (!raw) return null;
      return JSON.parse(raw) as DemoCheckoutSession;
    } catch (error) {
      this.logger.error(
        'Failed to read a demo checkout session',
        error instanceof Error ? error.stack : String(error),
      );
      return null;
    } finally {
      redis.disconnect();
    }
  }
}
