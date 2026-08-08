import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddIeltsSubScores1786124768112 implements MigrationInterface {
  name = 'AddIeltsSubScores1786124768112';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "ielts_listening" numeric(2,1)`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "ielts_reading" numeric(2,1)`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "ielts_writing" numeric(2,1)`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" ADD "ielts_speaking" numeric(2,1)`,
    );
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "ielts_speaking"`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "ielts_writing"`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "ielts_reading"`,
    );
    await queryRunner.query(
      `ALTER TABLE "user_profiles" DROP COLUMN "ielts_listening"`,
    );
  }
}
