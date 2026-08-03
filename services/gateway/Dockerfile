FROM golang:1.25-alpine AS base
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

# Dev target: hot reload via air

FROM base AS dev
RUN go install github.com/air-verse/air@latest
COPY . .
EXPOSE 8080
CMD ["air", "-c", ".air.toml"]

# Build stage for prod binary

FROM base AS builder
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /gateway .

# Prod target: minimal final image

FROM alpine:3.20 AS prod
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /gateway .
EXPOSE 8080
CMD ["./gateway"]