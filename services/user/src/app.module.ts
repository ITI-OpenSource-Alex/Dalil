import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ConfigModule } from '@nestjs/config';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { UsersModule } from './users/users.module';
import { typeOrmConfig } from './database/typeorm.config';
import { SqsModule } from './sqs/sqs.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    TypeOrmModule.forRoot(typeOrmConfig()),
    UsersModule,
    SqsModule,
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
