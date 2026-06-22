FROM golang:1.25-alpine AS base

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download


# Dev target reload via air
FROM base AS dev
RUN go install github.com/air-verse/air@latest
COPY . .
EXPOSE 8082
CMD ["air", "-c", ".air.toml"]

#Build Stage
FROM base AS builder
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /speaking ./cmd/speaking

# Production target (mini image)
FROM alpine:3.20 AS prod
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /speaking .
EXPOSE 8082
CMD ["./speaking"]