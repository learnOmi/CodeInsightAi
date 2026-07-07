FROM node:22-alpine AS base

FROM base AS deps
WORKDIR /app

COPY package.json package-lock.json* ./
COPY packages/shared/package.json ./packages/shared/
COPY codeinsight-frontend/package.json ./codeinsight-frontend/

RUN npm ci

FROM base AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build:shared
RUN npm run build:frontend

FROM base AS runner
WORKDIR /app

ENV NODE_ENV production

COPY --from=builder /app/codeinsight-frontend/public ./public
COPY --from=builder /app/codeinsight-frontend/.next/standalone ./
COPY --from=builder /app/codeinsight-frontend/.next/static ./.next/static

EXPOSE 3000

CMD ["node", "server.js"]