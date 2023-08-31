FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential autoconf automake pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/universal-ctags/ctags.git && \
    cd ctags && \
    ./autogen.sh && \
    ./configure --prefix=/app/ctags_build && \
    make && make install

COPY pyproject.toml ./

RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install sentence_transformers --no-cache-dir
RUN pip install --no-cache-dir poetry \
    && poetry export -f requirements.txt --without-hashes -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

FROM base as final

COPY sweepai /app/sweepai

EXPOSE 8080
CMD ["uvicorn", "sweepai.api:app", "--host", "0.0.0.0", "--port", "8080"]

LABEL org.opencontainers.image.description="Backend for Sweep, an AI-powered junior developer"
LABEL org.opencontainers.image.source="https://github.com/sweepai/sweep"
