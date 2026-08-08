import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * GOA-039 — the user ↔ Stripe Customer mapping.
 *
 * One nullable column, plus a partial unique index so two accounts cannot
 * claim the same Stripe customer while the (many) accounts that have never
 * opened a checkout stay NULL. A plain UNIQUE would work in Postgres too
 * (NULLs do not collide), but the partial index states the intent and keeps
 * the index off rows that will never be looked up by it.
 *
 * Deliberately NOT included: stripe_subscription_id, subscription_status and
 * subscription_expires_at. Those carry the subscription *lifecycle*, which is
 * GOA-078's scope; adding them here would create columns nothing reads or
 * maintains.
 */
export class AddStripeCustomerId1784000000000 implements MigrationInterface {
  name = 'AddStripeCustomerId1784000000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "users" ADD "stripe_customer_id" character varying`,
    );
    await queryRunner.query(
      `CREATE UNIQUE INDEX "IDX_users_stripe_customer_id" ON "users" ("stripe_customer_id") WHERE "stripe_customer_id" IS NOT NULL`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `DROP INDEX "public"."IDX_users_stripe_customer_id"`,
    );
    await queryRunner.query(
      `ALTER TABLE "users" DROP COLUMN "stripe_customer_id"`,
    );
  }
}
