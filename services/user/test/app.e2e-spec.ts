import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication, HttpStatus, ValidationPipe } from '@nestjs/common';
import * as request from 'supertest';
import { AppModule } from './../src/app.module';
import * as dotenv from 'dotenv';
import * as path from 'path';

dotenv.config({ path: path.resolve(__dirname, '../.env') });

describe('User Flow Integration (e2e)', () => {
  let app: INestApplication | undefined;
  let createdUserId: string;
  const internalApiKey =
    process.env.INTERNAL_API_KEY || 'supersecret_internal_key_123';

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    }).compile();

    app = moduleFixture.createNestApplication();
    app.useGlobalPipes(
      new ValidationPipe({
        whitelist: true,
        transform: true,
        errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY,
      }),
    );

    await app.init();
  });

  afterAll(async () => {
    await app?.close(); // 👈 safe navigation guards against init failure
  });

  // 1. Happy Path: Registration
  it('/users (POST) - should create a user and return the object without password hash', async () => {
    const email = `test-${Date.now()}@example.com`; // Unique runtime email seed
    const response = await request(app.getHttpServer())
      .post('/users')
      .send({ email, password: 'securePassword123' })
      .expect(HttpStatus.CREATED);

    expect(response.body).toHaveProperty('id');
    expect(response.body.email).toBe(email);
    expect(response.body).not.toHaveProperty('passwordHash');

    createdUserId = response.body.id; // Retain ID context for step propagation
  });

  // 2. Security Guard Constraint Path
  it('/users/:id (GET) - should deny access without service guard API Key', async () => {
    await request(app.getHttpServer())
      .get(`/users/${createdUserId}`)
      .expect(HttpStatus.UNAUTHORIZED);
  });

  // 3. Service Lookup Validation Path
  it('/users/:id (GET) - should fetch target model payload when providing correct service credentials', async () => {
    const response = await request(app.getHttpServer())
      .get(`/users/${createdUserId}`)
      .set('x-internal-api-key', internalApiKey)
      .expect(HttpStatus.OK);

    expect(response.body.id).toBe(createdUserId);
    expect(response.body).toHaveProperty('profile');
  });

  // 4. Input Constraints Guard Path
  it('/users/:id/profile (PUT) - should emit 422 payload rejection errors for invalid negative GPA constraints', async () => {
    const response = await request(app.getHttpServer())
      .put(`/users/${createdUserId}/profile`)
      .send({ gpa: -1.0, degreeLevel: 'Masters' })
      .expect(HttpStatus.UNPROCESSABLE_ENTITY);

    expect(response.body.message).toContain('GPA cannot be negative.');
  });


  describe('Internal Auth / Refresh Tokens (GOA-090)', () => {
    let testUserId: string;
    let validTokenId: string;
    let validRawToken: string;

    const testEmail = 'e2e-auth@example.com';
    const testPassword = 'securePassword123';

    it('should register a test user', async () => {
      const res = await request(app.getHttpServer())
        .post('/users')
        .send({ email: testEmail, password: testPassword })
        .expect(201);
      testUserId = res.body.id;
    });

    it('/internal/auth/login (POST) - atomic token creation', async () => {
      const res = await request(app.getHttpServer())
        .post('/internal/auth/login')
        .set('X-Internal-Api-Key', 'supersecret_internal_key_123')
        .send({ email: testEmail, password: testPassword, deviceHint: 'TestAgent' })
        .expect(200);

      expect(res.body).toHaveProperty('userId', testUserId);
      expect(res.body).toHaveProperty('email', testEmail);
      expect(res.body).toHaveProperty('tokenId');
      expect(res.body).toHaveProperty('rawToken');

      validTokenId = res.body.tokenId;
      validRawToken = res.body.rawToken;
    });

    it('/internal/auth/refresh-tokens (POST) - rotation', async () => {
      const res = await request(app.getHttpServer())
        .post('/internal/auth/refresh-tokens')
        .set('X-Internal-Api-Key', 'supersecret_internal_key_123')
        .send({ tokenId: validTokenId, rawToken: validRawToken })
        .expect(200);

      expect(res.body).toHaveProperty('newTokenId');
      expect(res.body).toHaveProperty('newRawToken');
      // The old token is now invalidated!
    });

    it('/internal/auth/refresh-tokens (POST) - REPLAY ATTACK', async () => {
      // Reusing the old (now revoked) token should trigger a 403 Forbidden
      await request(app.getHttpServer())
        .post('/internal/auth/refresh-tokens')
        .set('X-Internal-Api-Key', 'supersecret_internal_key_123')
        .send({ tokenId: validTokenId, rawToken: validRawToken })
        .expect(403);
    });
  });
});




