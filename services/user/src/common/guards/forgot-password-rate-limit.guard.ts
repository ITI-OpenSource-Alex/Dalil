import {
  Injectable,
  CanActivate,
  ExecutionContext,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
import Redis from 'ioredis';
import { Request } from 'express';
@Injectable()
export class ForgotPasswordRateLimitGuard implements CanActivate {
  private redis: Redis;

  constructor() {
    // Connect to your Redis cluster using environment parameters
    this.redis = new Redis({
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT || '6379', 10),
    });
  }

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<Request>();
    const email = (request.body as { email?: string })?.email;

    if (!email) {
      return true; // Let validation pipeline catch the missing email field
    }

    // Standardize key format based on target email
    const redisKey = `rate_limit:forgot_password:${email.toLowerCase().trim()}`;

    // Increment the counter for this email window
    const luaScript = `
  local count = redis.call('INCR', KEYS[1])
  if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
  end
  return count
`;
    const currentRequests = (await this.redis.eval(
      luaScript,
      1,
      redisKey,
      '3600',
    )) as number;

    // Enforce the threshold cap defined in the criteria
    if (currentRequests > 3) {
      throw new HttpException(
        {
          statusCode: HttpStatus.TOO_MANY_REQUESTS,
          error: 'Too Many Requests',
          message:
            'Too many password reset requests. Please try again in an hour.',
        },
        HttpStatus.TOO_MANY_REQUESTS,
      );
    }

    return true;
  }
}
