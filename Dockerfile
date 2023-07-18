# Start from a Python 3.10 base image
FROM python:3.10

# Install poetry
RUN pip install poetry

# Set the working directory to /app
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files into the Docker image
COPY pyproject.toml poetry.lock /app/

# Configure poetry to not create virtual environments
RUN poetry config virtualenvs.create false

# Install the dependencies using poetry
RUN cd /app && poetry install --no-root

# Copy the rest of the application into the Docker image
COPY . .

# RUN poetry install

# Set the default command to run Sweep Chat
CMD ["python", "-u", "sweepai/app/cli.py"]