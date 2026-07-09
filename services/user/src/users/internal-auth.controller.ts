import { Controller, Post, Body, UseGuards, HttpCode, HttpStatus } from '@nestjs/common';
import { UsersService } from './users.service';
import { InternalAuthGuard } from '../common/guards/internal-auth.guard';
import { InternalLoginDto, InternalRefreshDto, InternalRevokeDto } from './dto/refresh-token.dto';



@Controller('internal/auth')
@UseGuards(InternalAuthGuard)
export class InternalAuthController {
    constructor(private readonly usersService: UsersService) { }

    @Post('login')
    @HttpCode(HttpStatus.OK)
    async login(@Body() dto: InternalLoginDto) {
        return this.usersService.internalLogin(dto);
    }

    @Post('refresh-tokens')
    @HttpCode(HttpStatus.OK)
    async refreshTokens(@Body() dto: InternalRefreshDto) {
        return this.usersService.internalRefresh(dto);
    }

    @Post('revoke-tokens')
    @HttpCode(HttpStatus.OK)
    async revokeTokens(@Body() dto: InternalRevokeDto) {
        await this.usersService.internalRevoke(dto);
        return { success: true };
    }
}