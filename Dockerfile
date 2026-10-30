FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Libraries that Chrome needs to run headless
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates fonts-liberation \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
        libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
        libpango-1.0-0 libcairo2 libglib2.0-0 libx11-6 libxcb1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Chrome browser + ChromeDriver (matching versions) go to /opt
COPY install_chrome.py .
RUN python install_chrome.py \
    && chmod -R a+rx /opt/chrome-linux64 /opt/chromedriver-linux64

# Python packages (Selenium, Flask)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Selenium + summarizer + REST API
COPY app.py .

EXPOSE 7000

# API starts automatically when the container runs
CMD ["python", "app.py"]
