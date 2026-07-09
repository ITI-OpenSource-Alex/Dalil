import { IsEmail, IsNotEmpty, IsString, IsOptional, IsBoolean } from 'class-validator';


export class InternalLoginDto {
    @IsEmail({}, { message: 'Please provide a valid email address.' })
    email: string;


    @IsNotEmpty()
    @IsString()
    password: string;

    @IsOptional()
    @IsString()
    deviceHint?: string;
}

export class InternalRefreshDto {
    @IsNotEmpty()
    @IsString()
    tokenId: string;
    @IsNotEmpty()
    @IsString()
    rawToken: string;
    @IsOptional()
    @IsString()
    deviceHint?: string;
}

export class InternalRevokeDto {
    @IsNotEmpty()
    @IsString()
    userId: string;
    @IsOptional()
    @IsString()
    tokenId?: string;
    @IsNotEmpty()
    @IsBoolean()
    revokeAll: boolean;
}