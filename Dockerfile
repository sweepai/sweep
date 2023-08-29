# Use a lightweight base image
FROM python:3.11-slim as base

# Install Poetry
RUN pip install poetry

# Set working directory
WORKDIR /app

# Copy pyproject.toml and poetry.lock
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry export -f requirements.txt --without-hashes -o requirements.txt \
    && pip install -r requirements.txt

# Build final image
FROM base as final

# Copy code
COPY . /app

# Expose FastAPI port
EXPOSE 8000

# Run FastAPI
CMD ["uvicorn", "sweepai:app", "--host", "0.0.0.0", "--port", "8000"]
