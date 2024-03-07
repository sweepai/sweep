FROM python:3.10-slim as base

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV WORKERS=3
ENV PORT=${PORT:-8080}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl redis-server npm \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
ENV VIRTUAL_ENV=/usr/local
ADD --chmod=755 https://astral.sh/uv/install.sh /install.sh
RUN /install.sh && rm /install.sh

COPY requirements.txt ./

RUN /root/.cargo/bin/uv pip install --no-cache -r requirements.txt

RUN npm install -g prettier @types/react @types/react-dom typescript

COPY sweepai /app/sweepai
COPY tests /app/tests
ENV PYTHONPATH=.
COPY bin/startup.sh /app/startup.sh
COPY redis.conf /app/redis.conf
RUN chmod u+x /app/startup.sh

EXPOSE $PORT
CMD ["/app/startup.sh"]

LABEL org.opencontainers.image.description="Backend for Sweep, an AI-powered junior developer"
LABEL org.opencontainers.image.source="https://github.com/sweepai/sweep"
