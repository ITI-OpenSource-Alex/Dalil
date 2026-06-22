import {
  Controller,
  Post,
  Get,
  Put,
  Body,
  Param,
  UseGuards,
} from '@nestjs/common';

import { UsersService } from './users.service';
import { CreateUserDto } from './dto/create-user.dto';
import { InternalAuthGuard } from '../common/guards/internal-auth.guard';
import { UpdateProfileDto } from '../profile/dto/update-profile.dto';

@Controller('users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Post()
  register(@Body() createUserDto: CreateUserDto) {
    return this.usersService.register(createUserDto);
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
}
