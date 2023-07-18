# Start from a Python 3.10 base image
FROM python:3.10

# Set the working directory to /app
WORKDIR /app

# Copy the requirements.txt file into the Docker image
COPY requirements.txt ./

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application into the Docker image
COPY . .

# Set the default command to run Sweep Chat
CMD ["python", "sweep_chat.py"]