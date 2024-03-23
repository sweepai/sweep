FROM python:3.10-slim as base

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV WORKERS=3
ENV PORT=${PORT:-8080}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl redis-server npm build-essential pkg-config libssl-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LO https://github.com/BurntSushi/ripgrep/releases/download/13.0.0/ripgrep_13.0.0_amd64.deb && \
    dpkg -i ripgrep_13.0.0_amd64.deb && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y 
ENV PATH="/root/.cargo/bin:${PATH}"
RUN git clone https://github.com/BurntSushi/ripgrep
RUN cd ripgrep && \
    cargo build --release && \
    ./target/release/rg --version

ENV VIRTUAL_ENV=/usr/local
RUN curl -sSL https://astral.sh/uv/install.sh -o /install.sh && chmod 755 /install.sh && /install.sh && rm /install.sh

COPY requirements.txt ./

RUN /root/.cargo/bin/uv pip install --no-cache -r requirements.txt

RUN npm install -g prettier @types/react @types/react-dom typescript

COPY sweepai /app/sweepai
COPY tests /app/tests
ENV PYTHONPATH=.
COPY bin/startup.sh /app/startup.sh
COPY redis.conf /app/redis.conf

# Set the SWEEP_VERSION environment variable to the current date and time during image build
ARG SWEEP_VERSION
RUN export SWEEP_VERSION=${SWEEP_VERSION:-$(date +%Y%m%d%H%M)} && echo "SWEEP_VERSION=$SWEEP_VERSION" >> .env
RUN chmod u+x /app/startup.sh

EXPOSE $PORT
CMD ["/app/startup.sh"]

LABEL org.opencontainers.image.description="Backend for Sweep, an AI-powered junior developer"
LABEL org.opencontainers.image.source="https://github.com/sweepai/sweep"
