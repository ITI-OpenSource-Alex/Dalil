import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { UserProfile } from './entities/profile.entity';
import { UpdateProfileDto } from './dto/update-profile.dto';

@Injectable()
export class ProfilesService {
  constructor(
    @InjectRepository(UserProfile)
    private readonly profileRepository: Repository<UserProfile>,
  ) {}

  async updateProfile(
    userId: string,
    updateProfileDto: UpdateProfileDto,
  ): Promise<UserProfile> {
    const profile = await this.profileRepository.findOne({ where: { userId } });

    if (!profile) {
      throw new NotFoundException(`Profile for user ${userId} does not exist`);
    }

    // Merge the partial updates directly into the entity instances
    Object.assign(profile, updateProfileDto);
    return this.profileRepository.save(profile);
  }
}
