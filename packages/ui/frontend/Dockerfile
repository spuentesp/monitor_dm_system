# packages/ui/frontend/Dockerfile
# Next.js 15 production build using standalone output

FROM node:20-alpine AS builder
WORKDIR /app

# Build context is packages/ui/frontend/ (set in docker-compose)
COPY package*.json ./
RUN npm ci

COPY . .

# NEXT_PUBLIC_* vars are baked at build time. Leave this empty by default so
# browser calls use the same-origin Next /api proxy.
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# This app currently has no static public/ assets, but the standalone runtime
# copy step expects the directory to exist.
RUN mkdir -p public

RUN npm run build

# --------------------------------------------------------------------------- #
FROM node:20-alpine AS final
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
