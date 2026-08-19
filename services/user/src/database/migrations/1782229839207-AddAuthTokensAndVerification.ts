import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddAuthTokensAndVerification1782229839207 implements MigrationInterface {
  name = 'AddAuthTokensAndVerification1782229839207';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `CREATE TABLE "reset_tokens" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "token_hash" character varying(64) NOT NULL, "user_id" uuid NOT NULL, "expires_at" TIMESTAMP WITH TIME ZONE NOT NULL, "used_at" TIMESTAMP WITH TIME ZONE, "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), CONSTRAINT "PK_acd6ec48b54150b1736d0b454b9" PRIMARY KEY ("id"))`,
    );
    await queryRunner.query(
      `CREATE INDEX "IDX_76517aab310f5b7e0d7c00c6e1" ON "reset_tokens"  ("token_hash") `,
    );
    await queryRunner.query(
      `CREATE TABLE "email_verifications" ("id" uuid NOT NULL DEFAULT uuid_generate_v4(), "token_hash" character varying(64) NOT NULL, "user_id" uuid NOT NULL, "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(), CONSTRAINT "PK_c1ea2921e767f83cd44c0af203f" PRIMARY KEY ("id"))`,
    );
    await queryRunner.query(
      `CREATE INDEX "IDX_7939cc2e493281f265179fa86c" ON "email_verifications"  ("token_hash") `,
    );
    await queryRunner.query(
      `ALTER TABLE "users" ADD "is_verified" boolean NOT NULL DEFAULT false`,
    );
    await queryRunner.query(
      `ALTER TABLE "reset_tokens" ADD CONSTRAINT "FK_61c9431c5fe994696fe1760a4df" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`,
    );
    await queryRunner.query(
      `ALTER TABLE "email_verifications" ADD CONSTRAINT "FK_c4f1838323ae1dff5aa00148915" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "email_verifications" DROP CONSTRAINT "FK_c4f1838323ae1dff5aa00148915"`,
    );
    await queryRunner.query(
      `ALTER TABLE "reset_tokens" DROP CONSTRAINT "FK_61c9431c5fe994696fe1760a4df"`,
    );
    await queryRunner.query(`ALTER TABLE "users" DROP COLUMN "is_verified"`);
    await queryRunner.query(
      `DROP INDEX "public"."IDX_7939cc2e493281f265179fa86c"`,
    );
    await queryRunner.query(`DROP TABLE "email_verifications"`);
    await queryRunner.query(
      `DROP INDEX "public"."IDX_76517aab310f5b7e0d7c00c6e1"`,
    );
    await queryRunner.query(`DROP TABLE "reset_tokens"`);
  }
}
