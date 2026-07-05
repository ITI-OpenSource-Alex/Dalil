import { Injectable } from '@nestjs/common';
import { SqsMessageHandler } from '@ssut/nestjs-sqs'; // Or your custom handler decorator
import { MailerService } from '@nestjs-modules/mailer'; // Assumes NestJS Mailer layout

@Injectable()
export class NotificationConsumer {
  constructor(private readonly mailerService: MailerService) {}

  @SqsMessageHandler('PasswordResetRequested') // Match your SQS queue/event binding name
  async handlePasswordReset(message: any) {
    const { email, token } = JSON.parse(message.Body);

    await this.mailerService.sendMail({
      to: email,
      subject: 'Reset Your GOA Password',
      template: './password-reset', // Points to password-reset.hbs
      context: {
        token, // Passes the raw token to compile the dynamic URL path
      },
    });
  }

  @SqsMessageHandler('EmailVerificationRequired')
  async handleEmailVerification(message: any) {
    const { email, token } = JSON.parse(message.Body);

    await this.mailerService.sendMail({
      to: email,
      subject: 'Verify Your Email Address - GOA',
      template: './email-verify', // Points to email-verify.hbs
      context: {
        token,
      },
    });
  }
}
