# Railway Dockerfile for TPE Judicial Fulltext API
# Uses Playwright + Chromium for headless scraping of 司法院
# Pin to bookworm (Debian 12) for stable package names
FROM python:3.12-slim-bookworm

# Chromium system dependencies — install without --with-deps
# to avoid Ubuntu-only packages (ttf-ubuntu-font-family, ttf-unifont)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 \
    libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 \
    libxshmfence1 libx11-6 libx11-xcb1 libxcb1 libxext6 \
    libatk1.0-0 libatk-bridge2.0-0 libasound2 libcups2 \
    fonts-noto-cjk fonts-liberation fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's bundled Chromium binary only (no --with-deps)
RUN playwright install chromium

COPY . .

# Railway injects $PORT at runtime
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]

