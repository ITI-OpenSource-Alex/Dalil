import {
  Controller,
  Post,
  Get,
  Put,
  Body,
  Param,
  UseGuards,
  HttpCode,
  HttpStatus,
  Query,
} from '@nestjs/common';

import { UsersService } from './users.service';
import { CreateUserDto } from './dto/create-user.dto';
import { InternalAuthGuard } from '../common/guards/internal-auth.guard';
import { UpdateProfileDto } from '../profile/dto/update-profile.dto';
import { ForgotPasswordDto } from './dto/forgot-password.dto';
import { ResetPasswordDto } from './dto/reset-password.dto';
import { ForgotPasswordRateLimitGuard } from '../common/guards/forgot-password-rate-limit.guard';

@Controller('users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Post()
  register(@Body() createUserDto: CreateUserDto) {
    return this.usersService.register(createUserDto);
  }

  @Get('internal')
  @UseGuards(InternalAuthGuard)
  async findAllPaginated(
    @Query('page') page: string = '1',
    @Query('limit') limit: string = '50',
  ) {
    const pageNum = parseInt(page, 10) || 1;
    const limitNum = parseInt(limit, 10) || 50;
    return this.usersService.findAllPaginated(pageNum, limitNum);
  }

  @Get(':id')
  @UseGuards(InternalAuthGuard) // Service-to-service auth guard restriction
  findOne(@Param('id') id: string) {
    return this.usersService.findOneWithProfile(id);
  }

  @Put(':id/profile')
  updateProfile(@Param('id') id: string, @Body() dto: UpdateProfileDto) {
    return this.usersService.updateProfile(id, dto);
  }

  // --- Authentication Surface Endpoints ---

  @Post('../auth/forgot-password')
  @UseGuards(ForgotPasswordRateLimitGuard) // Rate limiting applied safely here
  @HttpCode(HttpStatus.OK) // Force 200 OK status to match specification requirements
  async forgotPassword(@Body() forgotPasswordDto: ForgotPasswordDto) {
    await this.usersService.forgotPassword(forgotPasswordDto);

    // Always return a static success message to prevent user enumeration attacks
    return {
      message:
        'If the email matches an account in our system, a reset link has been sent.',
    };
  }

  @Post('../auth/reset-password')
  @HttpCode(HttpStatus.OK)
  async resetPassword(@Body() resetPasswordDto: ResetPasswordDto) {
    await this.usersService.resetPassword(resetPasswordDto);
    return {
      message:
        'Password has been successfully reset. You can now log in with your new password.',
    };
  }

  @Get('../auth/verify-email/:token')
  async verifyEmail(@Param('token') token: string) {
    await this.usersService.verifyEmail(token);
    return {
      message:
        'Your email address has been verified successfully. Welcome aboard!',
    };
  }
}
