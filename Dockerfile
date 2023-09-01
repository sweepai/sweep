FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential autoconf automake pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN apt update && \
    apt-get install libjansson-dev && \
    git clone https://github.com/universal-ctags/ctags.git && \
    cd ctags && \
    ./autogen.sh && \
    ./configure && \
    make && make install

COPY pyproject.toml ./

RUN if [ "$(uname -m)" = "x86_64" ]; then \
    pip install torch --index-url https://download.pytorch.org/whl/cpu; \
  else \
    pip install torch; \
  fi
RUN pip install sentence_transformers --no-cache-dir
RUN pip install --no-cache-dir poetry \
    && poetry export -f requirements.txt --without-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

# Playwright
# Manually add Debian-based dependencies for Chromium
RUN apt-get install -y \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    wget
RUN apt-get install -y software-properties-common
RUN apt-add-repository non-free
RUN apt-add-repository contrib
RUN apt-get update
RUN pip install playwright==1.30.0
RUN playwright install
RUN pip install lxml

FROM base as final

COPY sweepai /app/sweepai

EXPOSE 8080
CMD ["uvicorn", "sweepai.api:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "3"]

LABEL org.opencontainers.image.description="Backend for Sweep, an AI-powered junior developer"
LABEL org.opencontainers.image.source="https://github.com/sweepai/sweep"
