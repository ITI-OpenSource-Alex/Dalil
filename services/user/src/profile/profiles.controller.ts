import { Controller, Put, Param, Body } from '@nestjs/common';
import { ProfilesService } from './profiles.service';
import { UpdateProfileDto } from './dto/update-profile.dto';

@Controller('users')
export class ProfilesController {
  constructor(private readonly profilesService: ProfilesService) {}

  @Put(':id/profile')
  update(
    @Param('id') userId: string,
    @Body() updateProfileDto: UpdateProfileDto,
  ) {
    return this.profilesService.updateProfile(userId, updateProfileDto);
  }
}
