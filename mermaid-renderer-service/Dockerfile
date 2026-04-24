FROM node:20-alpine

LABEL org.opencontainers.image.title="mermaid-renderer-service"
LABEL org.opencontainers.image.description="Small HTTP service that renders Mermaid source to PNG through Mermaid CLI."

RUN apk add --no-cache \
    ca-certificates \
    chromium \
    font-noto-cjk \
    font-noto-emoji \
    freetype \
    harfbuzz \
    nss \
    ttf-freefont

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev \
  && npm cache clean --force

COPY app ./app

ENV NODE_ENV=production
ENV PORT=8091
ENV SERVICE_VERSION=0.1.0
ENV MMD_CLI_PATH=/app/node_modules/.bin/mmdc
ENV MMD_TIMEOUT_SECONDS=30
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV PUPPETEER_CONFIG_FILE=/app/app/puppeteer-config.json

EXPOSE 8091

CMD ["node", "app/main.js"]
