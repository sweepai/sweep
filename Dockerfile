# Docker image that uses Python to deploy FastAPI 
# FROM ubuntu:20.04
FROM python:3.10-slim-buster

WORKDIR /src

ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install --without dev

# Git Config
#TODO(pzhao) add args to dockerfile for github creds
#TODO(pzhao) add gitpython helpers
RUN git config --global user.name "Pilot"
RUN git config --global user.email "pilot@pilot.com"

# Copy core files
COPY /src /app/src

# Expose the port
EXPOSE 8000

ENV PYTHONPATH /app/src
ENV WORKSPACE /app/workspace

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
