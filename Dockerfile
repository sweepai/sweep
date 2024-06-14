FROM python:3.10-slim as base

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV WORKERS=3
ENV PORT=${PORT:-8080}

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl redis-server npm build-essential pkg-config libssl-dev \
       cmake pkg-config libicu-dev zlib1g-dev libcurl4-openssl-dev libssl-dev ruby-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN gem install github-linguist

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

RUN pip install --no-cache -r requirements.txt

RUN npm install -g prettier@2.0.4 @types/react @types/react-dom typescript eslint@8.57.0 
RUN npm install react react-dom
RUN npm install @typescript-eslint/parser @typescript-eslint/eslint-plugin eslint-plugin-import eslint-plugin-react --save-dev

COPY sweepai /app/sweepai
COPY tests /app/tests
ENV PYTHONPATH=.
COPY redis.conf /app/redis.conf
COPY bin /app/bin
RUN chmod a+x /app/bin/startup.sh

EXPOSE 8080
CMD ["bash", "-c", "chmod a+x /app/bin/startup.sh && /app/bin/startup.sh"]

LABEL org.opencontainers.image.description="Backend for Sweep, an AI-powered junior developer"
LABEL org.opencontainers.image.source="https://github.com/sweepai/sweep"
