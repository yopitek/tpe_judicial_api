# Railway Dockerfile for TPE Judicial Fulltext API
# Uses Playwright + Chromium for headless scraping of 司法院
FROM python:3.12-slim

# System deps for Chromium (playwright install-deps equivalent)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 \
    libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 libxshmfence1 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser (system deps already installed above)
RUN playwright install chromium

COPY . .

# Railway injects $PORT at runtime — do NOT hardcode port here
# The start command in railway.json uses $PORT
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}"]
