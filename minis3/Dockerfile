FROM python:3.10-slim-buster
WORKDIR /app
COPY ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY ./ /app/
EXPOSE 80
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
