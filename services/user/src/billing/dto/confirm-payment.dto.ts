import { IsString, Length, Matches } from 'class-validator';

/**
 * The body of POST /billing/demo/confirm.
 *
 * No user id and no tier: the caller says which checkout it is settling and
 * what was typed into the card field, and nothing else. Who the checkout
 * belongs to comes from the token's server-side record, and what the payment
 * did comes from the demo card table.
 */
export class ConfirmPaymentDto {
  /** Opaque, server-minted. 32 bytes rendered as hex. */
  @IsString()
  @Matches(/^[a-f0-9]{64}$/, { message: 'token must be a checkout token' })
  token: string;

  /**
   * Digits and formatting characters only, and bounded -- this is validation,
   * not a Luhn check, because a demo card is matched against a fixed table.
   */
  @IsString()
  @Length(12, 32)
  @Matches(/^[0-9 -]+$/, { message: 'cardNumber must contain digits only' })
  cardNumber: string;
}
