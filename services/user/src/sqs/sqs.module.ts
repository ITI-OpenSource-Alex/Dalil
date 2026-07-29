import { Module, Global } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { SqsModule as NestjsSqsModule } from '@ssut/nestjs-sqs';
import { SQSClient } from '@aws-sdk/client-sqs';

@Global()
@Module({
  imports: [
    NestjsSqsModule.registerAsync({
      imports: [ConfigModule],
      useFactory: (configService: ConfigService) => {
        const region = configService.get<string>('AWS_REGION', 'us-east-1');
        const endpoint = configService.get<string>('AWS_ENDPOINT');
        const accessKeyId = configService.get<string>('AWS_ACCESS_KEY_ID');
        const secretAccessKey =
          configService.get<string>('AWS_SECRET_ACCESS_KEY');
        const queueUrl = configService.get<string>('SQS_QUEUE_URL');
        if (!queueUrl) {
          throw new Error('SQS_QUEUE_URL environment variable is required');
        }

        const sqsClient = new SQSClient({
          region,
          ...(endpoint && { endpoint }),
          ...(accessKeyId &&
            secretAccessKey && {
              credentials: { accessKeyId, secretAccessKey },
            }),
        });

        const producerName = configService.get<string>(
          'SQS_PRODUCER_NAME',
          'user-events',
        );

        return {
          consumers: [],
          producers: [
            {
              name: producerName,
              queueUrl,
              region,
              sqs: sqsClient,
            },
          ],
        };
      },
      inject: [ConfigService],
    }),
  ],
  exports: [NestjsSqsModule],
})
export class SqsModule {}
