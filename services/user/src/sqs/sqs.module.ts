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

        // GOA-083: a second producer targeting the Notification service's
        // queue. The User service no longer sends email directly — the
        // forgot-password and registration flows publish PasswordResetRequested
        // / EmailVerificationRequired events here, and the Notification Lambda
        // (which already consumes notification-queue) renders and sends them.
        //
        // Registered only when NOTIFICATION_QUEUE_URL is set so that existing
        // environments and unit tests that don't need it still boot. The
        // service logs and no-ops if it's asked to publish without it.
        const notificationProducerName = configService.get<string>(
          'SQS_NOTIFICATION_PRODUCER_NAME',
          'notifications',
        );
        const notificationQueueUrl = configService.get<string>(
          'NOTIFICATION_QUEUE_URL',
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
            ...(notificationQueueUrl
              ? [
                  {
                    name: notificationProducerName,
                    queueUrl: notificationQueueUrl,
                    region,
                    sqs: sqsClient,
                  },
                ]
              : []),
          ],
        };
      },
      inject: [ConfigService],
    }),
  ],
  exports: [NestjsSqsModule],
})
export class SqsModule {}
