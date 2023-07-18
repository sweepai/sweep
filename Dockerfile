# Start from a Python 3.10 base image
FROM python:3.10

# Set the working directory to /app
WORKDIR /app

# Copy the pyproject.toml and poetry.lock files into the Docker image
COPY pyproject.toml poetry.lock ./

# Install poetry
RUN pip install poetry

# Configure poetry to not create virtual environments
RUN poetry config virtualenvs.create false

# Install the dependencies using poetry
RUN poetry install --no-dev

# Copy the rest of the application into the Docker image
COPY . .

# Set the default command to run Sweep Chat
CMD ["python", "sweep_chat.py"]