import {
  IsNumber,
  IsOptional,
  IsString,
  Min,
  Max,
  IsArray,
} from 'class-validator';

export class UpdateProfileDto {
  @IsOptional()
  @IsString()
  degreeLevel?: string;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 2 })
  @Min(0, { message: 'GPA cannot be negative.' })
  @Max(4.0, { message: 'GPA cannot exceed 4.0.' })
  gpa?: number;

  @IsOptional()
  @IsNumber({ maxDecimalPlaces: 1 })
  @Min(0)
  @Max(9.0)
  ieltsScore?: number;

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
}
