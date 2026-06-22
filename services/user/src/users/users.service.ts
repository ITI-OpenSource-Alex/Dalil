import {
  Injectable,
  ConflictException,
  NotFoundException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { User } from './entities/user.entity';
import { UserProfile } from '../profile/entities/profile.entity';
import { CreateUserDto } from './dto/create-user.dto';
import { UpdateProfileDto } from '../profile/dto/update-profile.dto';
import * as bcrypt from 'bcrypt';

@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User) private readonly userRepository: Repository<User>,
    @InjectRepository(UserProfile)
    private readonly profileRepository: Repository<UserProfile>,
  ) {}

  // FIX 1: Async methods must return a Promise wrapper, and we type it cleanly using structural mapping
  async register(
    createUserDto: CreateUserDto,
  ): Promise<Omit<User, 'passwordHash'>> {
    const { email, password } = createUserDto;

    const passwordHash = await bcrypt.hash(password, 10);

    const user = this.userRepository.create({
      email,
      passwordHash,
    });

    try {
      const savedUser = await this.userRepository.save(user);

      const profile = this.profileRepository.create({
        userId: savedUser.id,
        targetCountries: [],
      });
      await this.profileRepository.save(profile);

      // Exclude passwordHash from the return payload
      const { passwordHash: _, ...result } = savedUser;
      return result;
    } catch (error: any) {
      if (error.code === '23505') {
        throw new ConflictException('Email address already registered');
      }
      throw error;
    }
  }

  async findOneWithProfile(id: string): Promise<User> {
    // FIX 2: Modern TypeORM requires an explicit boolean object assignment for relations mapping
    const user = await this.userRepository.findOne({
      where: { id },
      relations: {
        profile: true,
      },
    });

    if (!user) {
      throw new NotFoundException(`User with ID ${id} not found`);
    }

    // FIX 3: Instead of mutating the database entity with 'delete', we dynamically omit it safely
    const { passwordHash, ...userWithoutPassword } = user;
    return userWithoutPassword as User;
  }

  async updateProfile(id: string, dto: UpdateProfileDto): Promise<UserProfile> {
    const profile = await this.profileRepository.findOne({
      where: { userId: id },
    });

    if (!profile) {
      throw new NotFoundException(`Profile for user ${id} not found`);
    }

    Object.assign(profile, dto);
    return this.profileRepository.save(profile);
  }
}
