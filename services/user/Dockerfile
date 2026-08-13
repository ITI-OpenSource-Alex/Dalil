# --- STAGE 1: Build & Development Base ---
FROM node:20-alpine AS development

WORKDIR /usr/src/app

COPY package*.json ./

RUN npm ci

COPY . .

RUN npm run build

# 👇 ADD THIS LINE RIGHT HERE TO KICKSTART NESTJS
CMD ["npm", "run", "start:dev"]


# --- STAGE 2: Thin Production Runner ---
FROM node:20-alpine AS production

ARG NODE_ENV=production
ENV NODE_ENV=${NODE_ENV}

WORKDIR /usr/src/app

COPY package*.json ./

# Only install production dependencies (excludes devDependencies like testing tools)
RUN npm ci --only=production

# Copy built code from the development stage
COPY --from=development /usr/src/app/dist ./dist

# GOA-030: the Amazon RDS root CA bundle.
#
# RDS presents a certificate signed by an Amazon CA that is not in Node's
# bundled trust store, so connecting to a managed Postgres died with
# SELF_SIGNED_CERT_IN_CHAIN before a single migration ran. The Python services
# never hit this: asyncpg defaults to sslmode=prefer and does not verify the
# chain, so this service looked uniquely broken when it was the only one
# actually checking.
#
# Baked in rather than fetched at runtime -- it is ~200 KB, it changes about
# once every few years, and a runtime download would make database connectivity
# depend on egress to a third party.
#
# PGSSLROOTCERT is read by data-source.ts. Unset, the service connects with no
# TLS configuration, which is what a plaintext local Postgres wants.
RUN apk add --no-cache curl \
    && curl -fsSL -o /etc/ssl/certs/rds-global-bundle.pem \
       https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
    && apk del curl
ENV PGSSLROOTCERT=/etc/ssl/certs/rds-global-bundle.pem

CMD ["node", "dist/main"]