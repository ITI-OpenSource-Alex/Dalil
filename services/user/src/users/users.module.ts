import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { UsersService } from './users.service';
import { UsersController } from './users.controller';
import { User } from './entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { ResetToken } from './entities/reset-tokens.entity';
import { EmailVerification } from './entities/email-verification.entity';

@Module({
  imports: [
    // Register both repositories so they can be injected into the service
    TypeOrmModule.forFeature([
      User,
      UserProfile,
      ResetToken,
      EmailVerification,
    ]),
  ],
  controllers: [UsersController],
  providers: [UsersService],
  exports: [UsersService], // Export if other modules need to find users
})
export class UsersModule {}
