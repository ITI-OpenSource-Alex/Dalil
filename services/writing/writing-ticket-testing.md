# GOA — Writing Upload Ticket: Summary & Testing Notes

## Objective

This ticket focused on validating the **essay upload flow** through the **Gateway** into the **Writing service**, making sure that:

- authentication works correctly
- Gateway validation is enforced
- requests reach the Writing service and are persisted
- supported and unsupported file uploads are handled correctly

---

# 1) Services used during testing

The following services were involved in testing:

- `gateway` on `http://localhost:8080`
- `writing` on `http://localhost:8000`
- `user-service` on `http://localhost:8081`
- `postgres`
- `redis-gateway`

### Important note

At first, there was confusion around the user service name.  
The correct service name in `docker-compose.yml` is:

```yaml
user-service:
```

not `user`.

---

# 2) Authentication flow confirmed during testing

From reviewing the current Gateway auth flow, the following was confirmed:

## Login route

- **Method:** `POST`
- **Path:** `/auth/login`

## Login request body

```json
{
  "email": "test@example.com",
  "password": "my_password123"
}
```

## Login response

The Gateway returns:

- `access_token`
- `refresh_token`

It also sets **HTTP cookies** for:

- `access_token`
- `refresh_token`

### Important detail

The Gateway accepts authentication in **two ways**:

1. `Authorization: Bearer <token>`
2. `access_token` cookie

This was confirmed during testing when a request still succeeded after removing the Authorization header, because Postman was still sending the stored auth cookies from the previous login.

---

# 3) Test user creation

Since there was no seeded user available, a test user was created manually through `user-service`.

## Request

**POST** `http://localhost:8081/users`

### Headers

```http
Content-Type: application/json
X-Internal-Api-Key: supersecret_internal_key_123
```

### Body

```json
{
  "email": "test@example.com",
  "password": "my_password123",
  "name": "Test User"
}
```

## Result

The request returned `201 Created`, and the user was successfully created.

---

# 4) Login

After creating the user, login was tested through the Gateway.

## Request

**POST** `http://localhost:8080/auth/login`

### Body

```json
{
  "email": "test@example.com",
  "password": "my_password123"
}
```

## Result

The response returned:

- `access_token`
- `refresh_token`

This token was then used for the upload tests.

---

# 5) Main endpoint tested

The main endpoint covered by this ticket was:

```http
POST http://localhost:8080/api/writing/essays/upload
```

This route is accessed through the Gateway and then forwarded to the Writing service.

---

# 6) Tests performed

---

## Test 1 — Happy path (essay text only)

### Goal

Verify that a basic essay upload works end-to-end through the Gateway into the Writing service.

### Request

**POST** `http://localhost:8080/api/writing/essays/upload`

### Headers

```http
Authorization: Bearer <access_token>
```

### Body → form-data

- `essayText = This is my IELTS essay text`
- `submissionType = ielts`
- `examSessionId = exam-123`

## Result

The request returned:

```json
{
  "id": 6,
  "status": "ready",
  "s3Key": null
}
```

### Conclusion

- the Gateway accepted the request successfully
- authentication worked correctly
- the request was forwarded to the Writing service
- the essay was stored successfully

---

## Test 2 — Verify persistence inside the Writing service

### Goal

Confirm that the essay was actually stored in the Writing service after upload.

### Request

**GET** `http://localhost:8000/essays/6`

## Result

The response returned the stored essay data, including:

- `id`
- `userId`
- `s3Key`
- `extractedText`
- `uploadedAt`
- `status`
- `submissionType`
- `examSessionId`

Example response:

```json
{
  "id": 6,
  "userId": "0a298ca6-8b5c-4583-b0af-81dd25d5c536",
  "s3Key": null,
  "extractedText": "This is my IELTS essay text",
  "uploadedAt": "2026-07-06T13:19:44.518071",
  "status": "ready",
  "submissionType": "ielts",
  "examSessionId": "exam-123"
}
```

### Conclusion

This confirmed that the upload was not just returning a success response, but that the essay was actually persisted inside the Writing service.

---

## Test 3 — Unauthorized request (without token / without cookies)

### Goal

Verify that the essay upload route is properly protected by JWT middleware.

### Scenario

The same upload request was sent **without Authorization header** and after removing auth cookies from Postman.

### Result

The response returned:

```http
401 Unauthorized
```

Response body:

```json
{
  "error": "missing or invalid authorization token"
}
```

### Conclusion

- the route is properly protected
- access without valid authentication is denied

---

## Test 4 — essayText longer than 5000 characters

### Goal

Verify that Gateway validation correctly rejects essay text that exceeds the maximum allowed length.

### Scenario

An upload request was sent with:

- `essayText` longer than 5000 characters
- a valid access token

### Result

The response returned:

```http
400 Bad Request
```

Response body:

```json
{
  "error": "essayText exceeds maximum length of 5000 characters"
}
```

### Conclusion

- the validation is working correctly in the Gateway
- the request is rejected before reaching the Writing service

---

## Test 5 — Happy path with supported file upload

### Goal

Verify that uploading a supported file along with the essay works successfully.

### Scenario

An upload request was sent with:

- `essayText`
- `submissionType`
- `examSessionId`
- `file = supported PDF`

### Result

The request succeeded with `200 OK`, and the response contained:

- `id`
- `status = ready`
- `s3Key` with a real uploaded path

Example:

```json
{
  "id": 9,
  "status": "ready",
  "s3Key": "uploads/<user-id>/<filename>.pdf"
}
```

### Conclusion

- supported file upload works correctly
- the file is processed and assigned an `s3Key`

---

## Test 6 — Unsupported file type

### Goal

Verify that unsupported file types are rejected.

### Scenario

An upload request was sent with:

- `essayText`
- `submissionType`
- `examSessionId`
- `file` with an unsupported file type

### Result

The response returned:

```http
415 Unsupported Media Type
```

Response body:

```json
{
  "detail": "Unsupported file type"
}
```

### Conclusion

- file type validation is working correctly
- unsupported file uploads are rejected as expected

---

# 7) Final testing summary

## Successfully verified

- test user creation and usage for authentication
- login flow through the Gateway
- JWT token retrieval and cookie-based auth behavior
- successful happy path upload
- actual persistence inside the Writing service
- JWT protection on the upload route
- essay length validation
- supported file upload
- unsupported file rejection

---

# 8) Final conclusion

From a **functional testing** perspective, this ticket is well covered across the key scenarios:

1. **Happy path**
2. **Authentication / authorization**
3. **Essay length validation**
4. **Supported file upload**
5. **Unsupported file rejection**
6. **Persistence verification in the Writing service**

At this stage, the writing upload ticket can be considered **working from a testing perspective** for the intended flow.
