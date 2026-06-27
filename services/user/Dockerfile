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

CMD ["node", "dist/main"]