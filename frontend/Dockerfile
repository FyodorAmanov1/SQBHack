# syntax=docker/dockerfile:1.6

# -------- deps ---------------------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app

# libc6-compat is required by several npm native addons on Alpine.
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json ./
RUN npm ci

# -------- build --------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

# Public env vars must be provided at build time because Next.js inlines them
# into the client bundle. Override via `--build-arg` in docker-compose or CLI.
# Overridden by docker-compose `build.args` (see root .env: PUBLIC_ORIGIN, WS_URL)
ARG NEXT_PUBLIC_WS_URL=ws://127.0.0.1/ws/voice
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ARG NEXT_PUBLIC_WS_API_KEY=
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL} \
    NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_WS_API_KEY=${NEXT_PUBLIC_WS_API_KEY} \
    NEXT_TELEMETRY_DISABLED=1

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

# -------- runtime ------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
