import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddTargetFieldOfStudy1786200000000 implements MigrationInterface {
  name = 'AddTargetFieldOfStudy1786200000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "target_field_of_study" character varying`,
    );
    // Backward-compatible default: existing users only had one study-field
    // value. Preserve their current matching behaviour until they edit the new
    // intended-field control.
    await queryRunner.query(
      `UPDATE "user_profiles" SET "target_field_of_study" = "fieldOfStudy" WHERE "target_field_of_study" IS NULL`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "target_field_of_study"`,
    );
  }
}
