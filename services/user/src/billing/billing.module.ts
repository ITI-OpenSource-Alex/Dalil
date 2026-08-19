import { Module } from '@nestjs/common';
import { BillingController } from './billing.controller';
import { BillingService } from './billing.service';
import { DemoCheckoutStore } from './demo-checkout.store';
import { UsersModule } from '../users/users.module';

/**
 * GOA-039 demo billing. Imports UsersModule rather than reaching for the User
 * repository itself: `subscriptionTier` has exactly one writer
 * (UsersService.updateSubscription), which is also where the Gateway's
 * subscription cache is invalidated.
 */
@Module({
  imports: [UsersModule],
  controllers: [BillingController],
  providers: [BillingService, DemoCheckoutStore],
})
export class BillingModule {}
