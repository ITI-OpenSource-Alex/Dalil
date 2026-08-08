import {
  Body,
  Controller,
  Headers,
  HttpCode,
  HttpStatus,
  Post,
  UnauthorizedException,
  UseGuards,
} from '@nestjs/common';
import { BillingService } from './billing.service';
import { CreateCheckoutDto } from './dto/create-checkout.dto';
import { ConfirmPaymentDto } from './dto/confirm-payment.dto';
import { InternalAuthGuard } from '../common/guards/internal-auth.guard';

/**
 * Demo billing routes (GOA-039).
 *
 * All three are internal: the Gateway is the only caller, and it supplies
 * X-User-Id from the validated JWT. Nothing here is reachable from a browser
 * directly, and none of these routes accepts an identity from its payload.
 *
 * There is no webhook. Demo billing has no external provider to call back, so
 * the outcome is settled synchronously by /billing/demo/confirm. The frontend
 * still refuses to treat its own redirect as proof and re-reads the profile.
 */
@Controller('billing')
@UseGuards(InternalAuthGuard)
export class BillingController {
  constructor(private readonly billingService: BillingService) {}

  private requireUser(userId?: string): string {
    // Set by the Gateway from the validated token. Its absence means the route
    // was reached some other way, which is a bug rather than a login prompt.
    if (!userId) {
      throw new UnauthorizedException('Missing authenticated user');
    }
    return userId;
  }

  @Post('checkout')
  async createCheckout(
    @Body() dto: CreateCheckoutDto,
    @Headers('x-user-id') userId?: string,
  ) {
    return this.billingService.createCheckoutSession(
      this.requireUser(userId),
      dto.successUrl,
      dto.cancelUrl,
    );
  }

  /**
   * Settles the demo payment.
   *
   * 200 for both outcomes: a declined card is a normal result the page needs
   * to render, not a transport error. Only a spent, expired or stolen token
   * produces a 4xx.
   */
  @Post('demo/confirm')
  @HttpCode(HttpStatus.OK)
  async confirmPayment(
    @Body() dto: ConfirmPaymentDto,
    @Headers('x-user-id') userId?: string,
  ) {
    return this.billingService.confirmPayment(
      this.requireUser(userId),
      dto.token,
      dto.cardNumber,
    );
  }

  @Post('cancel')
  @HttpCode(HttpStatus.OK)
  async cancel(@Headers('x-user-id') userId?: string) {
    return this.billingService.cancelSubscription(this.requireUser(userId));
  }
}
