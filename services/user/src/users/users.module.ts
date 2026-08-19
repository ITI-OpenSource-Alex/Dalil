import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { UsersService } from './users.service';
import { UsersController } from './users.controller';
import { AuthController } from './auth.controller';
import { User } from './entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { ResetToken } from './entities/reset-tokens.entity';
import { EmailVerification } from './entities/email-verification.entity';
import { RefreshToken } from './entities/refresh-token.entity';
import { InternalAuthController } from './internal-auth.controller';
import { SubscriptionCacheService } from '../common/redis/subscription-cache.service';
@Module({
  imports: [
    // Register both repositories so they can be injected into the service
    TypeOrmModule.forFeature([
      User,
      UserProfile,
      ResetToken,
      EmailVerification,
      RefreshToken,
    ]),
  ],
  controllers: [UsersController, InternalAuthController, AuthController],
  providers: [UsersService, SubscriptionCacheService],
  // BillingModule consumes UsersService so that subscriptionTier keeps a
  // single writer (GOA-039).
  exports: [UsersService],
})
export class UsersModule {}
