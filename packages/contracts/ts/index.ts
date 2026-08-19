export interface BaseEvent {
    type: string;
    version: '1.0';
    timestamp: string; //ISO 8601
    correlationId: string;
}

export interface UserUpdated extends BaseEvent {
  type: "user.updated";
  payload: {
    userId: string;
    email: string;
    subscriptionTier: "free" | "paid";
    ects: number;
    gpa: number;
    gpaScale: "4.0" | "100";
    ieltsScore: number;
    ieltsListening: number | null;
    ieltsReading: number | null;
    ieltsWriting: number | null;
    ieltsSpeaking: number | null;
    degreeLevel: string;
    workExperienceYears: number;
    extracurricularsScore: number;
    targetCountries: string[];
    fieldOfStudy: string | null;
    targetFieldOfStudy: string | null;
  };
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
    type: 'cv.processed';
    payload: {
        userId: string;
        extractedText: string;
        status: 'success' | 'failed';
    }
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


export type DomainEvent =
    | UserUpdated
    | CVUploaded
    | CVProcessed
    | ScholarshipMatched
    | NotificationRequested
    | IngestionCompleted;
