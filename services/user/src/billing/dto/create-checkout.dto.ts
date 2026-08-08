import { IsUrl } from 'class-validator';

/**
 * The body of POST /billing/checkout, as forwarded by the Gateway.
 *
 * Note what is NOT here: a user id (the Gateway derives it from the JWT and
 * sends it as X-User-Id), a price, and a tier. A request shape with no field
 * for them cannot be tricked into honouring one.
 *
 * The URLs are re-validated as URLs here for shape, but the security decision
 * — that they point at an origin we own — is made in the Gateway, which is
 * the layer that knows CORS_ALLOWED_ORIGINS. See handlers/billing.go.
 */
// require_tld is off so `http://localhost:3000` passes in development.
// require_protocol and require_host are on because without them class-validator
// treats a bare word like "not-a-url" as a valid hostname, and this constraint
// would accept anything at all.
const RETURN_URL = {
  require_tld: false,
  require_protocol: true,
  require_host: true,
  protocols: ['http', 'https'],
};

export class CreateCheckoutDto {
  @IsUrl(RETURN_URL)
  successUrl: string;

  @IsUrl(RETURN_URL)
  cancelUrl: string;
}
