export interface BaseEvent {
    type: string;
    version: '1.0';
    timestamp: string; //ISO 8601
    correlationId: string;
}

export interface UserUpdated extends BaseEvent {
    type: 'user.updated';
    payload: {
        userId: string;
        email: string;
        subscriptionTier: 'free' | 'paid';
    }
}

export interface CVUploaded extends BaseEvent {
    type: 'cv.uploaded';
    payload: {
        userId: string;
        s3Key: string;
        fileName: string;
    }
}

export interface CVProcessed extends BaseEvent {
    type: 'CVProcessed';
    userId: string;
    cvId: number;
    s3Key: string;
    status: 'ready' | 'failed';
}

export interface ScholarshipMatched extends BaseEvent {
    type: 'scholarship.matched';
    payload: {
        userId: string;
        programId: string;
        score: number;
    };
}

export interface NotificationRequested extends BaseEvent {
    type: 'notification.requested';
    payload: {
        userId: string;
        template: 'password_reset' | 'email_verify' | 'scholarship_alert';
        recipientEmail: string;
        templateData: Record<string, string | number>;
    };
}

export interface IngestionCompleted extends BaseEvent {
    type: 'ingestion.completed';
    payload: {
        sourceUrl: string;
        chunksCreated: number;
    };
}


export type NotificationEventType =
    | 'ScholarshipMatched'
    | 'DEADLINE_REMINDER'
    | 'CVProcessed';

export interface ScholarshipMatchedNotification {
    eventType: 'ScholarshipMatched';
    userId: string;
    programId: string;
    programName: string | null;
    provider: string | null;
    country: string | null;
    deadline: string | null;
    score: number;
    cycleDate: string;
}

export interface DeadlineReminderNotification {
    eventType: 'DEADLINE_REMINDER';
    userId: string;
    programId: string;
    programName: string | null;
    provider: string | null;
    country: string | null;
    deadline: string | null;
    score: number;
    cycleDate: string;
}

export interface CVProcessedNotification {
    eventType: 'CVProcessed';
    userId: string;
    cvId: number;
    s3Key: string;
    status: 'ready' | 'failed';
    timestamp?: string;
    correlationId?: string;
}

export type NotificationEvent =
    | ScholarshipMatchedNotification
    | DeadlineReminderNotification
    | CVProcessedNotification;

export type DomainEvent =
    | UserUpdated
    | CVUploaded
    | CVProcessed
    | ScholarshipMatched
    | NotificationRequested
    | IngestionCompleted;
