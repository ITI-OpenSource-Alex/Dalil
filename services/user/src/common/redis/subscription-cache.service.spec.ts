import { SubscriptionCacheService } from './subscription-cache.service';

const mockDel = jest.fn();
const mockDisconnect = jest.fn();

jest.mock('ioredis', () => ({
  __esModule: true,
  default: jest.fn().mockImplementation(() => ({
    del: mockDel,
    disconnect: mockDisconnect,
  })),
}));

describe('SubscriptionCacheService', () => {
  let service: SubscriptionCacheService;

  beforeEach(() => {
    jest.clearAllMocks();
    mockDel.mockResolvedValue(1);
    service = new SubscriptionCacheService();
  });

  it('builds the exact key the Go Gateway reads', () => {
    // Must match middleware.SubscriptionCacheKey in services/gateway. If these
    // ever drift, a paid user keeps getting 403 until the TTL expires and
    // nothing in either codebase says why.
    expect(SubscriptionCacheService.key('user-1')).toBe('subtier:v1:user-1');
  });

  it('deletes the cached tier so the next request re-reads the database', async () => {
    await service.invalidate('user-1');

    expect(mockDel).toHaveBeenCalledWith('subtier:v1:user-1');
    expect(mockDisconnect).toHaveBeenCalled();
  });

  it('swallows a Redis failure rather than failing the payment', async () => {
    // The tier is already committed. Throwing here would fail the upgrade
    // request after the subscription had in fact been granted.
    mockDel.mockRejectedValue(new Error('connection refused'));

    await expect(service.invalidate('user-1')).resolves.toBeUndefined();
    expect(mockDisconnect).toHaveBeenCalled();
  });
});
