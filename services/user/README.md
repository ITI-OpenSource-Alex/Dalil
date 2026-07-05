# User Service

The User service is a NestJS application that manages user registration, credential hashing using bcrypt, profile information, password reset workflows, and email verification.

---

## What it Owns

* **Responsibility**: Authenticating user credentials, managing user profiles (GPA, IELTS scores, target study countries), and generating email verification and password reset tokens.
* **Database**: Connects to PostgreSQL (`user_db`). Manages `users`, `user_profiles`, and `refresh_tokens` tables.
* **Queues**: Publishes `user.updated` and `notification.requested` events to LocalStack SQS.

---

## API Reference

*Note: All endpoints are protected internally and require the `X-Internal-Api-Key` header.*

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
* **Response Shape (200 OK)**: `{"status": "success", "message": "Password reset successfully"}`

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
