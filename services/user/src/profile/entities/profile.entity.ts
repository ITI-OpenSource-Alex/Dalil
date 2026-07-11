import { Entity, Column, OneToOne, JoinColumn, PrimaryColumn } from 'typeorm';
import { User } from '../../users/entities/user.entity';

@Entity('user_profiles')
export class UserProfile {
  // Using the userId directly as the Primary Key for a strict 1:1 pairing
  @PrimaryColumn('uuid')
  userId: string;

  @Column({ nullable: true })
  degreeLevel: string;

  @Column({ type: 'decimal', precision: 3, scale: 2, nullable: true })
  gpa: number;

  @Column({ type: 'decimal', precision: 2, scale: 1, nullable: true })
  ieltsScore: number;

  // maps to text[] in PostgreSQL for native array storage
  @Column('text', { array: true, default: '{}' })
  targetCountries: string[];

  @Column({ nullable: true })
  fieldOfStudy: string;

  @Column({ type: 'int', nullable: true })
  ects: number;


  @Column({ name: 'work_experience_years', type: 'int', default: 0 })
  workExperienceYears: number;


  @Column({ name: 'extracurriculars_score', type: 'int', default: 0 })
  extracurricularsScore: number;

  @Column({ name: 'gpa_scale', type: 'varchar', length: 4, default: '100' })
  gpaScale: '4.0' | '100';

  @OneToOne(() => User, (user) => user.profile, { onDelete: 'CASCADE' })
  @JoinColumn({ name: 'userId' })
  user: User;
}
