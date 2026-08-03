# Gateway Service

The Gateway service is the secure entry point for all client requests. It handles path routing, JWT access token authentication, token revocation checks via Redis, rate-limiting, and request logging.

---

## What it Owns

* **Responsibility**: Routing requests, validating user authentication JWTs, checking the Redis JTI token blacklist, and rate-limiting incoming client traffic.
* **Database**: Connects to `redis-gateway` (logical db 0) for access token JTI revocation blacklisting.
* **Queues**: N/A (Does not subscribe or publish to queues).

---

## API Reference

### 1. `POST /auth/login`
* **Auth Required**: No
* **Request Shape**:
```json
{
  "email": "user@example.com",
  "password": "secretpassword"
}
```
* **Response Shape (200 OK)**:
```json
{
  "accessToken": "eyJhbGciOi...",
  "expiresIn": 3600
}
```
* **Cookies Set**: Sets `refresh_token` as an `httpOnly` cookie.
* **Error Codes**:
  * `400 Bad Request`: Malformed body parameters.
  * `401 Unauthorized`: Invalid credentials.

### 2. `POST /auth/refresh`
* **Auth Required**: No (Uses `refresh_token` cookie)
* **Request Shape**: Empty body.
* **Response Shape (200 OK)**:
```json
{
  "accessToken": "eyJhbGciOi...",
  "expiresIn": 3600
}
```
* **Error Codes**:
  * `401 Unauthorized`: Expired or revoked refresh token.

### 3. `POST /auth/logout`
* **Auth Required**: Yes
* **Request Shape**: Empty body.
* **Response Shape (200 OK)**:
```json
{
  "status": "success",
  "message": "Logged out successfully"
}
```
* **Description**: Revokes the refresh token, invalidates the client cookie, and writes the current access token `jti` to the Redis blacklist with a TTL equal to the token's remaining lifespan.

### 4. `POST /auth/logout-all`
* **Auth Required**: Yes
* **Request Shape**: Empty body.
* **Response Shape (200 OK)**:
```json
{
  "status": "success",
  "message": "Logged out from all devices"
}
```
* **Description**: Revokes all refresh tokens registered for this user in the User database.

### 5. `POST /auth/forgot-password`
* **Auth Required**: No
* **Request Shape**: `{"email": "user@example.com"}`
* **Response Shape (200 OK)**: `{"message": "If the email matches an account in our system, a reset link has been sent."}`
* **Description**: Plain proxy to the User Service's `POST /auth/forgot-password` — always 200 regardless of whether the email exists, and rate-limited per email (3 requests/hour) by the User Service.

### 6. `POST /auth/reset-password`
* **Auth Required**: No
* **Request Shape**: `{"token": "reset_token_xyz", "newPassword": "newpassword123"}`
* **Response Shape (200 OK)**: `{"message": "Password has been successfully reset. You can now log in with your new password."}`
* **Description**: Plain proxy to the User Service's `POST /auth/reset-password`. A successful reset revokes every existing refresh token for that user.

### 7. `GET /auth/verify-email/:token`
* **Auth Required**: No
* **Response Shape (200 OK)**: `{"message": "Your email address has been verified successfully. Welcome aboard!"}`
* **Description**: Plain proxy to the User Service's `GET /auth/verify-email/:token`.

### 8. `GET /health`
* **Auth Required**: No
* **Response Shape (200 OK)**:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime": "2h45m"
}
```

---

## Environment Variables

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `PORT` | Local network port the gateway binds to. | `8080` |
| `JWT_SECRET` | Secret key used to sign and verify Access JWT tokens (HS256). | `supersecretkey` |
| `REDIS_URL` | Connection URI for the Redis blacklist database. | `redis://redis-gateway:6379/0` |
| `USER_SERVICE_URL` | Downstream connection URL for User authentication. | `http://user:8081` |
| `ORCHESTRATION_SERVICE_URL` | Downstream connection URL for Orchestrator routing. | `http://orchestration:8083` |

---

## How to Run Locally

### Running outside Docker
```bash
go run main.go
```

### Running with Docker
```bash
docker compose up -d gateway
```
The gateway service will listen on `http://localhost:8080`.

---

## How to Run Tests

```bash
# Run unit and integration tests
go test ./...
```
