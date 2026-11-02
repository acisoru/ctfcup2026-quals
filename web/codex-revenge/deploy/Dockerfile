FROM node:current-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
    libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libnspr4 libnss3 libpango-1.0-0 \
    libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 \
    unzip \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm install --omit=dev \
 && rm -rf /root/.cache/puppeteer \
 && npx --yes puppeteer browsers install chrome@159.0.8132.0 \
 && ln -sf /root/.cache/puppeteer/chrome/linux*/chrome-linux*/chrome /usr/local/bin/chrome

ENV PUPPETEER_EXECUTABLE_PATH=/usr/local/bin/chrome

COPY server.js bot.js ./
COPY public/ public/
COPY data/ data/

EXPOSE 3000
CMD ["node", "server.js"]
