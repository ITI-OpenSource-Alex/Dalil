import {
  IsNumber,
  IsOptional,
  IsString,
  Min,
  Max,
  IsArray,
  IsInt,
  IsIn,
} from 'class-validator';

export class UpdateProfileDto {
  @IsOptional()
  @IsString()
  degreeLevel?: string;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 2 })
  @Min(0, { message: 'GPA cannot be negative.' })
  @Max(100, { message: 'GPA cannot exceed 100.' })
  gpa?: number;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 1 })
  @Min(0)
  @Max(9.0)
  ieltsScore?: number;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 1 })
  @Min(0)
  @Max(9.0)
  ieltsListening?: number;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 1 })
  @Min(0)
  @Max(9.0)
  ieltsReading?: number;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 1 })
  @Min(0)
  @Max(9.0)
  ieltsWriting?: number;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 1 })
  @Min(0)
  @Max(9.0)
  ieltsSpeaking?: number;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  targetCountries?: string[];

  @IsOptional()
  @IsString()
  fieldOfStudy?: string;

  @IsOptional()
  @IsNumber()
  ects?: number;

  @IsOptional()
  @IsInt()
  @Min(0)
  workExperienceYears?: number;
  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(10)
  extracurricularsScore?: number;
  @IsOptional()
  @IsIn(['4.0', '100'])
  gpaScale?: '4.0' | '100';
}
