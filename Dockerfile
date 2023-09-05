FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV WORKERS=3

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential autoconf automake pkg-config libjansson-dev docker.io \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/universal-ctags/ctags.git && \
    cd ctags && \
    ./autogen.sh && \
    ./configure && \
    make && make install

RUN if [ "$(uname -m)" = "x86_64" ]; then \
    pip install torch --index-url https://download.pytorch.org/whl/cpu; \
  else \
    pip install torch; \
  fi && pip install sentence_transformers --no-cache-dir

COPY pyproject.toml ./

RUN pip install --no-cache-dir poetry \
    && poetry export -f requirements.txt --without-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

RUN playwright install
RUN apt-get update && apt-get install -y screen
RUN apt-get update && apt-get install -y redis-server

FROM base as final

COPY sweepai /app/sweepai
COPY bin/startup.sh /app/startup.sh
RUN chmod u+x /app/startup.sh

# Has some startup logic
RUN python sweepai/startup.py

EXPOSE 8080
CMD ["/app/startup.sh"]

LABEL org.opencontainers.image.description="Backend for Sweep, an AI-powered junior developer"
LABEL org.opencontainers.image.source="https://github.com/sweepai/sweep"
