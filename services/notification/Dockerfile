# Notification service — Lambda container image.
#
# BUILD CONTEXT IS THE REPOSITORY ROOT, not services/notification:
#
#   docker build -f services/notification/Dockerfile -t goa-notification .
#
# The context must be the root because src/events.ts and src/templates.ts import
# the shared event contract from packages/contracts/ts, and tsc needs that file
# present at build time. A build scoped to services/notification cannot see it
# and fails with TS6059 — which is what the previous Dockerfile did.
#
# Terraform expects an image, not a zip: infra/terraform/main.tf sets
# package_type = "Image" on module.notification_sender_lambda.
#
# Two stages, because tsconfig's rootDir is the repo root (it has to be, to
# include the contract) and so the emitted tree mirrors the repo layout. The
# builder keeps that layout; the runtime image takes only the flattened output,
# so the Lambda handler string stays a plain "handler.handler".

# --- build ------------------------------------------------------------------
FROM node:20-slim AS builder

WORKDIR /repo

COPY services/notification/package*.json services/notification/
# Full install: typescript is a devDependency and the build needs it. The
# previous Dockerfile ran `npm ci --only=production` and then invoked npx tsc,
# which strips the compiler and then calls it.
RUN cd services/notification && npm ci

COPY packages/contracts/ts/index.ts packages/contracts/ts/index.ts
COPY services/notification/tsconfig.json services/notification/tsconfig.json
COPY services/notification/src/ services/notification/src/
COPY services/notification/templates/ services/notification/templates/

RUN cd services/notification && npm run build

# Runtime dependencies only, for the image below.
RUN cd services/notification && npm prune --omit=dev

# --- runtime ----------------------------------------------------------------
FROM public.ecr.aws/lambda/nodejs:20

WORKDIR ${LAMBDA_TASK_ROOT}

# Only the service's own compiled output. The contract is a type-only import and
# is erased at compile time — the emitted events.js requires nothing but crypto —
# so packages/contracts is a build-time dependency and never ships.
COPY --from=builder /repo/services/notification/dist/services/notification/src/ ./
COPY --from=builder /repo/services/notification/templates/ ./templates/
COPY --from=builder /repo/services/notification/node_modules/ ./node_modules/

CMD [ "handler.handler" ]
