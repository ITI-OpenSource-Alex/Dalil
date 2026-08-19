# User Service

The User service is a NestJS application that manages user registration, credential hashing using bcrypt, profile information, password reset workflows, and email verification.

---

## What it Owns

* **Responsibility**: Authenticating user credentials, managing user profiles (GPA, IELTS scores, target study countries), and generating email verification and password reset tokens.
* **Database**: Connects to PostgreSQL (`user_db`). Manages `users`, `user_profiles`, and `refresh_tokens` tables.
* **Queues**: Publishes `user.updated` and `notification.requested` events to LocalStack SQS.

---

## API Reference

*Note: `GET /users/internal`, `GET /users/:id`, and everything under `/internal/auth/*` require the `X-Internal-Api-Key` header and are only meant to be called by the Gateway. `POST /users` and everything under `/auth/*` below are public-facing.*

### 1. `POST /users`
* **Request Shape**:
```json
{
  "email": "student@example.com",
  "password": "strongpassword123",
  "name": "John Doe"
}
```
* **Response Shape (201 Created)**:
```json
{
  "id": "usr_abc123",
  "email": "student@example.com",
  "name": "John Doe",
  "subscriptionTier": "free",
  "createdAt": "2026-06-28T01:00:00Z"
}
```
* **Error Codes**:
  * `400 Bad Request`: Validation failure (e.g. invalid email format).
  * `409 Conflict`: User with this email already exists.

### 2. `GET /users/:id`
* **Response Shape (200 OK)**:
```json
{
  "id": "usr_abc123",
  "email": "student@example.com",
  "name": "John Doe",
  "subscriptionTier": "free",
  "profile": {
    "degreeLevel": "Bachelor",
    "gpa": 3.7,
    "ieltsScore": 7.5,
    "targetCountries": ["Germany", "Canada"],
    "fieldOfStudy": "Computer Science"
  }
}
```

### 3. `PUT /users/:id/profile`
* **Request Shape**:
```json
{
  "degreeLevel": "Master",
  "gpa": 3.8,
  "ieltsScore": 8.0,
  "targetCountries": ["Germany"],
  "fieldOfStudy": "Software Engineering"
}
```
* **Response Shape (200 OK)**:
```json
{
  "status": "success",
  "message": "Profile updated successfully"
}
```
* **Error Codes**:
  * `422 Unprocessable Entity`: Field validation failed (e.g. GPA out of bounds `> 4.0`).

### 4. `POST /auth/forgot-password`
* **Request Shape**: `{"email": "student@example.com"}`
* **Response Shape (200 OK)**: `{"message": "If the email exists, a reset link has been sent."}`
* **Description**: Generates a 32-byte hash reset token, stores it, and dispatches a notification request event. Returns 200 regardless of email existence to prevent user enumeration.

### 5. `POST /auth/reset-password`
* **Request Shape**: `{"token": "reset_token_xyz", "newPassword": "newpassword123"}`
* **Response Shape (200 OK)**: `{"message": "Password has been successfully reset. You can now log in with your new password."}`
* **Description**: Revokes every existing refresh token for the user as part of the same transaction, so any session issued before the reset (including one held by an attacker) is terminated.

### 6. `GET /auth/verify-email/:token`
* **Response Shape (200 OK)**: `{"message": "Your email address has been verified successfully. Welcome aboard!"}`
* **Error Codes**:
  * `400 Bad Request`: Token is invalid, already used, or unknown.

---

## Email Delivery (Local/Test Environments)

Verification and password-reset links are **not** sent through LocalStack SES or SQS in this environment — that path is intentionally not wired up (SES isn't enabled in the LocalStack container, and no notification service currently consumes those events). Instead, `register()` and `forgotPassword()` write the link directly to the service's stdout as a single structured line:

```
[SQS Simulation] Send verification email to user@example.com with link: https://goa.app/verify-email/<token>
[SQS Simulation] Send email to user@example.com with link: https://goa.app/reset-password?token=<token>
```

To retrieve a token during manual or automated testing, read the `user-service` container logs (`docker compose logs user-service`) and grab the token from the relevant line. If real email delivery via SES/SQS becomes a requirement, that work should enable `ses` in `infra/localstack`, uncomment/implement the SQS publish calls in `UsersService`, and register a consumer for the `EmailVerificationRequired` / `PasswordResetRequested` events — none of that exists today, so partially wiring only one side of it would be worse than the current log-based approach.

---

## Environment Variables

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `PORT` | NestJS server port binding. | `8081` |
| `DATABASE_URL` | PostgreSQL user database connection URL. | `postgresql://goa:goa_pass@postgres:5432/user_db` |
| `INTERNAL_API_KEY` | Secret token used to authenticate gateway-to-service internal calls. | `supersecret_internal_key_123` |
| `AWS_REGION` | AWS target region for SQS interactions. | `us-east-1` |
| `LOCALSTACK_URL` | LocalStack connection host for local development. | `http://localstack:4566` |

---

## How to Run Locally

### Running outside Docker
```bash
npm install
npm run start:dev
```

### Running with Docker
```bash
docker compose up -d user
```

---

## How to Run Tests

```bash
# Run unit tests
npm run test

# Run e2e tests
npm run test:e2e
```
