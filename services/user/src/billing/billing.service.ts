import {
  BadRequestException,
  ConflictException,
  Injectable,
  Logger,
  ServiceUnavailableException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { UsersService } from '../users/users.service';
import { DemoCheckoutStore } from './demo-checkout.store';

/**
 * Demo billing (GOA-039).
 *
 * This project needs to demonstrate a subscription upgrade, not process money.
 * So there is no payment provider here: no Stripe, no API keys, no external
 * callback. The checkout happens on a page this app serves, and the outcome is
 * decided by this service from a table of demo card numbers.
 *
 * WHAT THIS IS NOT
 * ================
 * This is not an authorization boundary and it takes no payment. Anyone who
 * can reach the confirm endpoint can grant themselves the paid tier by
 * submitting the success card -- that is the whole point of a demo, and it is
 * why `requireEnabled` refuses to run when NODE_ENV is production. Shipping
 * this to a real deployment would be giving the product away.
 *
 * WHAT IS DELIBERATELY REAL
 * =========================
 * Everything on our side of the payment. The tier is written server-side by
 * the same single writer a real provider would call
 * (UsersService.updateSubscription), the Gateway's subscription cache is
 * invalidated the same way, and the confirmation page still refuses to believe
 * a redirect and polls GET /api/profile instead. Swapping the demo for a real
 * provider later replaces this file and nothing around it.
 */

/**
 * The outcome of each demo card, decided server-side.
 *
 * The two numbers are the ones GOA-039's definition of done names, so the
 * acceptance scenarios are runnable locally rather than being blocked on an
 * external account.
 */
const DEMO_CARDS: Record<
  string,
  { status: 'succeeded' } | { status: 'declined'; message: string }
> = {
  '4242424242424242': { status: 'succeeded' },
  '4000000000009995': {
    status: 'declined',
    message: 'Your card has insufficient funds.',
  },
};

const GENERIC_DECLINE =
  'That card was declined. Use 4242 4242 4242 4242 to simulate a successful payment.';

export type DemoPaymentResult =
  | { status: 'succeeded'; redirectUrl: string }
  | { status: 'declined'; message: string };

@Injectable()
export class BillingService {
  private readonly logger = new Logger(BillingService.name);
  private readonly mode: string;

  constructor(
    private readonly configService: ConfigService,
    private readonly usersService: UsersService,
    private readonly checkoutStore: DemoCheckoutStore,
  ) {
    this.mode = (this.configService.get<string>('BILLING_MODE') ?? 'demo')
      .trim()
      .toLowerCase();

    if (this.mode === 'demo' && process.env.NODE_ENV === 'production') {
      this.logger.error(
        'BILLING_MODE=demo in a production build; billing endpoints are disabled. ' +
          'Demo billing grants the paid tier without taking payment.',
      );
    } else if (this.mode === 'demo') {
      this.logger.warn(
        'Billing is running in DEMO mode: upgrades are simulated and take no payment.',
      );
    }
  }

  /** False when billing is switched off, or would be unsafe to run. */
  isEnabled(): boolean {
    if (this.mode !== 'demo') return false;
    // A demo that hands out paid subscriptions must never answer in
    // production, whatever the configuration says.
    return process.env.NODE_ENV !== 'production';
  }

  private requireEnabled(): void {
    if (!this.isEnabled()) {
      throw new ServiceUnavailableException(
        'Billing is not available on this environment',
      );
    }
  }

  /**
   * Opens a demo checkout for the authenticated user.
   *
   * `userId` comes from the Gateway, which derives it from the validated JWT.
   * The return URLs have already been checked against the Gateway's allow-list
   * of origins we own; they are stored with the session so the demo page can
   * honour the caller's own success URL without ever accepting one from the
   * browser at confirm time.
   */
  async createCheckoutSession(
    userId: string,
    successUrl: string,
    cancelUrl: string,
  ): Promise<{ token: string }> {
    this.requireEnabled();

    const user = await this.usersService.findById(userId);

    // Selling a second subscription to someone who already has the plan would
    // be wrong even when no money changes hands -- the UI would offer an
    // upgrade that does nothing.
    if (user.subscriptionTier === 'paid') {
      throw new ConflictException('This account already has Dalil Pro');
    }

    const token = await this.checkoutStore.create(
      user.id,
      successUrl,
      cancelUrl,
    );
    this.logger.log(`Opened a demo checkout for user ${user.id}`);
    return { token };
  }

  /**
   * Settles a demo checkout.
   *
   * The token is the authority on *whose* checkout this is: it was minted
   * server-side and carries the user it belongs to, so a caller cannot settle
   * somebody else's session by editing a payload. It is consumed atomically,
   * so a double submit cannot upgrade twice or resurrect a declined attempt.
   *
   * A decline is a normal outcome, not an error: the caller gets 200 with
   * `status: "declined"` so the page can show the message and let them retry,
   * exactly as a hosted payment page would.
   */
  async confirmPayment(
    userId: string,
    token: string,
    cardNumber: string,
  ): Promise<DemoPaymentResult> {
    this.requireEnabled();

    const session = await this.checkoutStore.consume(token);
    if (!session) {
      throw new BadRequestException(
        'This checkout has expired or has already been used. Please start again.',
      );
    }

    if (session.userId !== userId) {
      // Someone is holding a token that is not theirs. The session is already
      // consumed by the read above, so the attempt is spent either way.
      this.logger.warn(
        `Demo checkout token for user ${session.userId} presented by user ${userId}`,
      );
      throw new BadRequestException('This checkout does not belong to you');
    }

    // Digits only: a demo card typed with spaces is the same card.
    const digits = cardNumber.replace(/\D/g, '');
    const outcome = DEMO_CARDS[digits];

    // The card number is never logged, even a fake one -- logging card-shaped
    // strings is a habit worth not forming.
    if (!outcome) {
      this.logger.log(`Demo payment declined for user ${userId}`);
      return { status: 'declined', message: GENERIC_DECLINE };
    }
    if (outcome.status === 'declined') {
      this.logger.log(`Demo payment declined for user ${userId}`);
      return { status: 'declined', message: outcome.message };
    }

    // The only place the tier is granted, and it goes through the same writer
    // a real payment provider's callback would use -- which is also what
    // invalidates the Gateway's cached tier.
    await this.usersService.updateSubscription(userId, 'paid');
    this.logger.log(`Demo payment succeeded; user ${userId} upgraded to paid`);

    return { status: 'succeeded', redirectUrl: session.successUrl };
  }

  /**
   * Cancels a subscription (GOA-039's "manage subscription" criterion).
   *
   * With no payment provider there is no hosted portal to link to, so the
   * product owns this: an in-app page calls here and the tier drops back to
   * free immediately. A real provider would instead schedule the downgrade for
   * the end of the paid period and tell us via a webhook -- see the report.
   */
  async cancelSubscription(
    userId: string,
  ): Promise<{ subscriptionTier: string }> {
    this.requireEnabled();

    const user = await this.usersService.findById(userId);
    if (user.subscriptionTier !== 'paid') {
      throw new ConflictException('This account is not on a paid plan');
    }

    const result = await this.usersService.updateSubscription(userId, 'free');
    this.logger.log(`Demo subscription cancelled for user ${userId}`);
    return result;
  }
}
