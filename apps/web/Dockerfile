# Next.js web image for the Guest Simulation Alpha prototype stack.
# Build context is the repository root (pnpm workspace lockfile lives there):
#   docker build -f apps/web/Dockerfile .
# The standalone server proxies /api/* to FastAPI (see apps/web/next.config.ts),
# so browsers only ever see one HTTPS origin.

FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.14.4 --activate

FROM base AS deps
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN pnpm install --frozen-lockfile --filter web

FROM base AS build
WORKDIR /repo
COPY --from=deps /repo ./
COPY apps/web ./apps/web
COPY packages/contracts ./packages/contracts
# Baked at build time (standalone output): the rewrite target must match the
# API service name in compose.prototype.yaml, and the browser-visible API base
# stays same-origin (/api) so no second origin ever appears.
ARG API_PROXY_TARGET=http://api:8000
ARG NEXT_PUBLIC_API_BASE=/api
ENV API_PROXY_TARGET=$API_PROXY_TARGET \
    NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_OUTPUT_STANDALONE=true \
    NEXT_TELEMETRY_DISABLED=1
RUN pnpm --dir apps/web exec next build

FROM node:22-alpine AS runtime
RUN addgroup --system --gid 10001 web && adduser --system --uid 10001 web

WORKDIR /srv
COPY --from=build --chown=web:web /repo/apps/web/.next/standalone ./
COPY --from=build --chown=web:web /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=web:web /repo/apps/web/public ./apps/web/public

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    NEXT_TELEMETRY_DISABLED=1

USER web
EXPOSE 3000

CMD ["node", "apps/web/server.js"]
