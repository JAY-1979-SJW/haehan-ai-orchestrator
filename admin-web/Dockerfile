# Stage 1: deps
FROM node:20-alpine AS deps
WORKDIR /repo/admin-web
COPY admin-web/package.json admin-web/package-lock.json ./
COPY admin-web/vendor ./vendor
RUN npm ci

# Stage 2: builder
FROM node:20-alpine AS builder
WORKDIR /repo
COPY --from=deps /repo/admin-web/node_modules ./admin-web/node_modules
COPY admin-web ./admin-web
WORKDIR /repo/admin-web
RUN npm run build

# Stage 3: runner
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV MARKET_RESEARCH_REPO_ROOT=/app

RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs \
 && apk add --no-cache python3

COPY --from=builder --chown=nextjs:nodejs /repo/admin-web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /repo/admin-web/.next/static ./.next/static
COPY --chown=nextjs:nodejs scripts ./scripts
COPY --chown=nextjs:nodejs security_utils.py ./security_utils.py

RUN mkdir -p /app/data /app/docs/reports \
 && chown -R nextjs:nodejs /app/data /app/docs

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
