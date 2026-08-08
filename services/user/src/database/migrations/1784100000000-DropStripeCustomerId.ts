import { MigrationInterface, QueryRunner } from 'typeorm';

/**
 * Drops the Stripe customer mapping (GOA-039).
 *
 * The subscription flow was re-scoped to a self-contained demo payment for the
 * graduation project: no Stripe, no external provider, no customer records to
 * map onto. `stripe_customer_id` therefore has nothing to hold and no reader,
 * and a column named after a vendor the system does not integrate with is
 * actively misleading to the next person reading the schema.
 *
 * Forward-only rather than editing 1784000000000-AddStripeCustomerId: that
 * migration has already run in local databases, and rewriting an applied
 * migration leaves those schemas silently out of step with the file that
 * claims to describe them.
 *
 * `down` restores the column and its partial unique index, so the pair is
 * reversible if a real payment provider is introduced later.
 */
export class DropStripeCustomerId1784100000000 implements MigrationInterface {
  name = 'DropStripeCustomerId1784100000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `DROP INDEX IF EXISTS "public"."IDX_users_stripe_customer_id"`,
    );
    await queryRunner.query(
      `ALTER TABLE "users" DROP COLUMN IF EXISTS "stripe_customer_id"`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "users" ADD "stripe_customer_id" character varying`,
    );
    await queryRunner.query(
      `CREATE UNIQUE INDEX "IDX_users_stripe_customer_id" ON "users" ("stripe_customer_id") WHERE "stripe_customer_id" IS NOT NULL`,
    );
  }
}
