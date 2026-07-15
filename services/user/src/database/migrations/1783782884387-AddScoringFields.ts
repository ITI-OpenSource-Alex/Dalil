import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddScoringFields1783782884387 implements MigrationInterface {
  name = 'AddScoringFields1783782884387';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "refresh_tokens" DROP CONSTRAINT "FK_refresh_tokens_user_id"`,
    );
    await queryRunner.query(
      `DROP INDEX "public"."IDX_refresh_tokens_token_hash"`,
    );
    await queryRunner.query(`DROP INDEX "public"."IDX_refresh_tokens_user_id"`);
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "work_experience_years" integer NOT NULL DEFAULT '0'`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "extracurriculars_score" integer NOT NULL DEFAULT '0' CHECK ("extracurriculars_score" BETWEEN 0 AND 10)`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "gpa_scale" character varying(4) NOT NULL DEFAULT '100' CHECK ("gpa_scale" IN ('4.0','100'))`,
    );
    await queryRunner.query(
      `CREATE INDEX "IDX_a7838d2ba25be1342091b6695f" ON "refresh_tokens"  ("token_hash") `,
    );
    await queryRunner.query(
      `ALTER TABLE "refresh_tokens" ADD CONSTRAINT "FK_3ddc983c5f7bcf132fd8732c3f4" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "refresh_tokens" DROP CONSTRAINT "FK_3ddc983c5f7bcf132fd8732c3f4"`,
    );
    await queryRunner.query(
      `DROP INDEX "public"."IDX_a7838d2ba25be1342091b6695f"`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "gpa_scale"`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "extracurriculars_score"`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "work_experience_years"`,
    );
    await queryRunner.query(
      `CREATE INDEX "IDX_refresh_tokens_user_id" ON "refresh_tokens" USING btree ("user_id") `,
    );
    await queryRunner.query(
      `CREATE INDEX "IDX_refresh_tokens_token_hash" ON "refresh_tokens" USING btree ("token_hash") `,
    );
    await queryRunner.query(
      `ALTER TABLE "refresh_tokens" ADD CONSTRAINT "FK_refresh_tokens_user_id" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE NO ACTION`,
    );
  }
}
