import { TypeOrmModuleOptions } from '@nestjs/typeorm';
import { AppDataSource } from './data-source';

export const typeOrmConfig = (): TypeOrmModuleOptions => ({
  ...AppDataSource.options,
  autoLoadEntities: true, // NestJS-specific, not in DataSource options
  synchronize: false,
  migrationsRun: true,
});
