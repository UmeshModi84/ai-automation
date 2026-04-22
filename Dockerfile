# Production image — non-root user, healthcheck
FROM node:20-alpine AS deps
WORKDIR /app
COPY app/package.json ./
RUN npm install --omit=dev --ignore-scripts

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -g 1001 -S nodejs && adduser -S nodejs -u 1001 -G nodejs \
  && apk add --no-cache wget
COPY --from=deps /app/node_modules ./node_modules
COPY app/package.json ./
COPY app/src ./src
COPY app/public ./public
USER nodejs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1
CMD ["node", "src/index.js"]
