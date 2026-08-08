import { IsIn } from 'class-validator';

/**
 * The body of PATCH /users/:id/subscription (GOA-039).
 *
 * `tier` is the only field, and it is constrained to the two values the User
 * entity and the Gateway both understand — anything else is rejected as 422 by
 * the global ValidationPipe rather than written to the column and discovered
 * later by the Gateway, which treats an unrecognised tier as an invalid
 * response from this service and fails closed to free.
 */
export class UpdateSubscriptionDto {
  @IsIn(['free', 'paid'])
  tier: 'free' | 'paid';
}
