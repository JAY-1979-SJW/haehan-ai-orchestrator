# Stage 1: deps
FROM node:24-bookworm-slim AS deps
WORKDIR /repo/admin-web
COPY admin-web/package.json admin-web/package-lock.json ./
COPY admin-web/vendor ./vendor
RUN npm ci

# Stage 2: builder
FROM node:24-bookworm-slim AS builder
WORKDIR /repo
COPY --from=deps /repo/admin-web/node_modules ./admin-web/node_modules
COPY admin-web ./admin-web
WORKDIR /repo/admin-web
RUN npm run build

# Stage 3: runner
FROM node:24-bookworm-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV MARKET_RESEARCH_REPO_ROOT=/app
ENV PATH=/opt/pydeps/bin:$PATH

RUN groupadd --system --gid 1001 nodejs \
 && useradd --system --uid 1001 --gid nodejs --home /app nextjs \
 && apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv python3-pip \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python3 -m venv /opt/pydeps \
 && /opt/pydeps/bin/pip install --no-cache-dir -r requirements.txt

COPY --from=builder --chown=nextjs:nodejs /repo/admin-web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/admin-web/.next/static ./.next/static
COPY --chown=nextjs:nodejs ai_orchestrator ./ai_orchestrator
COPY --chown=nextjs:nodejs scripts ./scripts

RUN mkdir -p /app/data /app/docs/reports \
 && chown -R nextjs:nodejs /app/data /app/docs

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
