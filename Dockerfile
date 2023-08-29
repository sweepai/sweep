FROM python:3.11-slim as base

RUN pip install poetry
WORKDIR /app
COPY pyproject.toml ./

RUN apt-get update && apt-get install -y build-essential
RUN poetry export -f requirements.txt --without-hashes -o requirements.txt
RUN pip install -r requirements.txt

FROM base as final
COPY . /app
EXPOSE 8000

CMD ["uvicorn", "sweepai:app", "--host", "0.0.0.0", "--port", "8000"]
