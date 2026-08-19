import { Injectable, Logger } from '@nestjs/common';
import Redis from 'ioredis';

/**
 * Drops the Gateway's cached view of a user's subscription tier.
 *
 * The Gateway does not ask this service for a tier on every request — it
 * caches the answer in Redis under `subtier:v1:<userId>` for
 * SUBSCRIPTION_CACHE_TTL (5 minutes by default, see gateway/config.go) and
 * fails closed to "free" on a cache miss it cannot resolve.
 *
 * That cache is what stands between a completed payment and a working paid
 * feature. Without this invalidation a user who has just paid keeps getting
 * 403 subscription_required for up to five minutes, which is both the single
 * most infuriating possible moment to be told no and a straight failure of
 * GOA-039's "paid features accessible within 5 seconds of redirect".
 *
 * Writing into another service's keyspace is not new here: revokeAllAccessTokens
 * in UsersService already stamps `user_revoked_before:{userId}` for the same
 * Gateway to read. The key format below must match
 * `middleware.SubscriptionCacheKey` in the Go Gateway exactly; the two are
 * coupled and there is no way to make that coupling invisible, only explicit.
 *
 * A client is opened per call rather than held for the lifetime of the
 * process, matching revokeAllAccessTokens. This path runs once per upgrade,
 * so a pooled connection would buy nothing and cost a lifecycle hook.
 */
@Injectable()
export class SubscriptionCacheService {
  private readonly logger = new Logger(SubscriptionCacheService.name);

  /** Must match middleware.SubscriptionCacheKey in the Gateway. */
  static key(userId: string): string {
    return `subtier:v1:${userId}`;
  }

  /**
   * Best-effort. A failure here is logged loudly but never thrown: the tier
   * has already been committed to Postgres, and turning a cache problem into
   * a failed upgrade would tell the user their payment did not work when it
   * did. The stale entry expires on its own within the TTL.
   */
  async invalidate(userId: string): Promise<void> {
    const redis = new Redis({
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT || '6379', 10),
      // Do not let a Redis outage hold the upgrade response open while the
      // user watches a spinner.
      maxRetriesPerRequest: 1,
    });

    try {
      await redis.del(SubscriptionCacheService.key(userId));
      this.logger.log(`Invalidated subscription cache for user ${userId}`);
    } catch (error) {
      this.logger.error(
        `Failed to invalidate the subscription cache for user ${userId}; ` +
          `paid features may lag by up to SUBSCRIPTION_CACHE_TTL`,
        error instanceof Error ? error.stack : String(error),
      );
    } finally {
      redis.disconnect();
    }
  }
}
