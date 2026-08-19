import { MigrationInterface, QueryRunner } from 'typeorm';

export class WidenProfileGpa1786600000000 implements MigrationInterface {
  name = 'WidenProfileGpa1786600000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      'ALTER TABLE "user_profiles" ALTER COLUMN "gpa" TYPE numeric(5,2)',
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      'ALTER TABLE "user_profiles" ALTER COLUMN "gpa" TYPE numeric(3,2)',
    );
  }
}
