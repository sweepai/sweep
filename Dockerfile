FROM python:3.11-slim as base

RUN apt-get update && apt-get install -y git build-essential
RUN pip install poetry
RUN pip install sentence_transformers==2.2.2
WORKDIR /app

COPY pyproject.toml ./
RUN poetry export -f requirements.txt --without-hashes -o requirements.txt
RUN pip install -r requirements.txt

FROM base as final
COPY sweepai /app/sweepai
EXPOSE 8000

CMD ["uvicorn", "sweepai.api:app", "--host", "0.0.0.0", "--port", "8000"]
