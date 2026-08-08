import { plainToInstance } from 'class-transformer';
import { validate } from 'class-validator';
import { UpdateSubscriptionDto } from './update-subscription.dto';

/**
 * The global ValidationPipe rejects with 422 on any failure here (see
 * main.ts), so these assertions are what stops an unrecognised tier reaching
 * the column. The Gateway treats a tier it does not recognise as an invalid
 * response from this service and fails closed to free — so a bad write would
 * silently lock a paying user out rather than throwing anywhere useful.
 */
async function errorsFor(payload: unknown) {
  const dto = plainToInstance(UpdateSubscriptionDto, payload);
  return validate(dto, { whitelist: true, forbidNonWhitelisted: false });
}

describe('UpdateSubscriptionDto', () => {
  it('accepts the two tiers the system understands', async () => {
    expect(await errorsFor({ tier: 'paid' })).toHaveLength(0);
    expect(await errorsFor({ tier: 'free' })).toHaveLength(0);
  });

  it.each([
    ['an unknown tier', { tier: 'premium' }],
    ['a casing variant', { tier: 'Paid' }],
    ['a missing tier', {}],
    ['a non-string tier', { tier: 1 }],
    ['a null tier', { tier: null }],
  ])('rejects %s', async (_label, payload) => {
    const errors = await errorsFor(payload);
    expect(errors.length).toBeGreaterThan(0);
    expect(errors[0].property).toBe('tier');
  });
});
