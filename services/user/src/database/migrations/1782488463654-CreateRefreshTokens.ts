import { MigrationInterface, QueryRunner } from 'typeorm';

export class CreateRefreshTokens1782329839208 implements MigrationInterface {
  name = 'CreateRefreshTokens1782329839208';

  public async up(queryRunner: QueryRunner): Promise<void> {
    // 1. Create the refresh_tokens table matching our entity columns
    await queryRunner.query(
      `CREATE TABLE "refresh_tokens" (
        "id" uuid NOT NULL DEFAULT uuid_generate_v4(), 
        "token_hash" character varying(255) NOT NULL, 
        "user_id" uuid NOT NULL, 
        "expires_at" TIMESTAMP WITH TIME ZONE NOT NULL, 
        "revoked_at" TIMESTAMP WITH TIME ZONE, 
        "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        "device_hint" character varying(255),
        CONSTRAINT "PK_refresh_tokens_id" PRIMARY KEY ("id")
      )`,
    );

    // 2. Add index for token_hash to speed up session validation lookups
    await queryRunner.query(
      `CREATE INDEX "IDX_refresh_tokens_token_hash" ON "refresh_tokens" ("token_hash")`,
    );

    // 3. Add index for user_id to speed up user session queries/revocations
    await queryRunner.query(
      `CREATE INDEX "IDX_refresh_tokens_user_id" ON "refresh_tokens" ("user_id")`,
    );

    // 4. Set up the foreign key relation referencing the users table
    await queryRunner.query(
      `ALTER TABLE "refresh_tokens" ADD CONSTRAINT "FK_refresh_tokens_user_id" 
       FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    // Revert foreign key, indices, and table in reverse order
    await queryRunner.query(
      `ALTER TABLE "refresh_tokens" DROP CONSTRAINT "FK_refresh_tokens_user_id"`,
    );
    await queryRunner.query(`DROP INDEX "IDX_refresh_tokens_user_id"`);
    await queryRunner.query(`DROP INDEX "IDX_refresh_tokens_token_hash"`);
    await queryRunner.query(`DROP TABLE "refresh_tokens"`);
  }
}
