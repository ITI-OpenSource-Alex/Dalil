import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import {
  ValidationPipe,
  HttpStatus,
  UnprocessableEntityException,
} from '@nestjs/common';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);

  // Global pipe configuration to satisfy the 422 Unprocessable Entity testing criteria
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
      errorHttpStatusCode: HttpStatus.UNPROCESSABLE_ENTITY, // Throws 422 automatically for invalid data (like negative GPA)
    }),
  );

  await app.listen(process.env.PORT || 8081);
}
bootstrap();