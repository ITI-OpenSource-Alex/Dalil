import {
  Controller,
  Post,
  Get,
  Put,
  Patch,
  Delete,
  Body,
  Param,
  UseGuards,
  Query,
  Headers,
  Header,
} from '@nestjs/common';

import { UsersService } from './users.service';
import { CreateUserDto } from './dto/create-user.dto';
import { InternalAuthGuard } from '../common/guards/internal-auth.guard';
import { UpdateProfileDto } from '../profile/dto/update-profile.dto';
import { DeleteAccountDto } from './dto/delete-account.dto';
import { UpdateSubscriptionDto } from './dto/update-subscription.dto';

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

  @Get(':id/subscription')
  @UseGuards(InternalAuthGuard)
  findSubscription(@Param('id') id: string) {
    return this.usersService.findSubscription(id);
  }

  /**
   * GOA-039. Service-to-service only, and deliberately so: this is the one
   * route in the product that can hand out paid access, so it must never be
   * reachable with nothing but a user's own session. The Gateway does not
   * proxy it — the only callers are billing (which runs inside this service
   * and calls UsersService directly) and an operator holding INTERNAL_API_KEY.
   */
  @Patch(':id/subscription')
  @UseGuards(InternalAuthGuard)
  updateSubscription(
    @Param('id') id: string,
    @Body() dto: UpdateSubscriptionDto,
  ) {
    return this.usersService.updateSubscription(id, dto.tier);
  }

  @Put(':id/profile')
  updateProfile(@Param('id') id: string, @Body() dto: UpdateProfileDto) {
    return this.usersService.updateProfile(id, dto);
  }

  @Delete(':id/account')
  deleteAccount(
    @Param('id') id: string,
    @Body() dto: DeleteAccountDto,
    @Headers('x-user-id') requesterId?: string,
  ) {
    return this.usersService.deleteAccount(id, requesterId, dto.confirmPassword);
  }

  @Get(':id/data-export')
  @Header('Content-Type', 'application/json')
  exportData(
    @Param('id') id: string,
    @Headers('x-user-id') requesterId?: string,
  ) {
    return this.usersService.exportUserData(id, requesterId);
  }
}

