import {
  Controller,
  Post,
  Get,
  Body,
  Param,
  HttpCode,
  HttpStatus,
  UseGuards,
} from '@nestjs/common';

import { UsersService } from './users.service';
import { ForgotPasswordDto } from './dto/forgot-password.dto';
import { ResetPasswordDto } from './dto/reset-password.dto';
import { ForgotPasswordRateLimitGuard } from '../common/guards/forgot-password-rate-limit.guard';

@Controller('auth')
export class AuthController {
  constructor(private readonly usersService: UsersService) {}

  @Post('forgot-password')
  @UseGuards(ForgotPasswordRateLimitGuard)
  @HttpCode(HttpStatus.OK) // Force 200 OK status to match specification requirements
  async forgotPassword(@Body() forgotPasswordDto: ForgotPasswordDto) {
    await this.usersService.forgotPassword(forgotPasswordDto);

    // Always return a static success message to prevent user enumeration attacks
    return {
      message:
        'If the email matches an account in our system, a reset link has been sent.',
    };
  }

  @Post('reset-password')
  @HttpCode(HttpStatus.OK)
  async resetPassword(@Body() resetPasswordDto: ResetPasswordDto) {
    await this.usersService.resetPassword(resetPasswordDto);
    return {
      message:
        'Password has been successfully reset. You can now log in with your new password.',
    };
  }

  @Get('verify-email/:token')
  async verifyEmail(@Param('token') token: string) {
    await this.usersService.verifyEmail(token);
    return {
      message:
        'Your email address has been verified successfully. Welcome aboard!',
    };
  }
}
