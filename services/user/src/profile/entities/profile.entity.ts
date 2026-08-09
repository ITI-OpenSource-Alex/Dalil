import { Entity, Column, OneToOne, JoinColumn, PrimaryColumn } from 'typeorm';
import { User } from '../../users/entities/user.entity';
import { numericTransformer } from '../../common/database/numeric.transformer';

@Entity('user_profiles')
export class UserProfile {
  // Using the userId directly as the Primary Key for a strict 1:1 pairing
  @PrimaryColumn('uuid')
  userId: string;

  @Column({ nullable: true })
  degreeLevel: string;

  // transformer: `numeric` arrives from the driver as a string. Without it these
  // two properties are typed `number` and are not one at runtime — see
  // common/database/numeric.transformer.ts.
  @Column({
    type: 'decimal',
    precision: 3,
    scale: 2,
    nullable: true,
    transformer: numericTransformer,
  })
  gpa: number;

  @Column({
    type: 'decimal',
    precision: 2,
    scale: 1,
    nullable: true,
    transformer: numericTransformer,
  })
  ieltsScore: number;

  // maps to text[] in PostgreSQL for native array storage
  @Column('text', { array: true, default: '{}' })
  targetCountries: string[];

  @Column({ nullable: true })
  fieldOfStudy: string;

  @Column({ name: 'target_field_of_study', nullable: true })
  targetFieldOfStudy: string | null;

  @Column({ type: 'int', nullable: true })
  ects: number;

  @Column({ name: 'work_experience_years', type: 'int', default: 0 })
  workExperienceYears: number;

  @Column({ name: 'extracurriculars_score', type: 'int', default: 0 })
  extracurricularsScore: number;

  @Column({ name: 'gpa_scale', type: 'varchar', length: 4, default: '100' })
  gpaScale: '4.0' | '100';

  @Column({
    name: 'ielts_listening',
    type: 'decimal',
    precision: 2,
    scale: 1,
    nullable: true,
  })
  ieltsListening: number | null;

  @Column({
    name: 'ielts_reading',
    type: 'decimal',
    precision: 2,
    scale: 1,
    nullable: true,
  })
  ieltsReading: number | null;

  @Column({
    name: 'ielts_writing',
    type: 'decimal',
    precision: 2,
    scale: 1,
    nullable: true,
  })
  ieltsWriting: number | null;

  @Column({
    name: 'ielts_speaking',
    type: 'decimal',
    precision: 2,
    scale: 1,
    nullable: true,
  })
  ieltsSpeaking: number | null;

  @OneToOne(() => User, (user) => user.profile, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'userId' })
  user: User;
}
