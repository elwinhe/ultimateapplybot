# Use a slim Python base image
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Copy requirements first to leverage layer caching
COPY ./sqs_consumer/requirements.txt .

# Install dependencies using uv
RUN pip install uv
RUN uv pip install --no-cache --system -r requirements.txt

# Copy the rest of the consumer's source code
COPY ./sqs_consumer/ .

# The command to run when the container starts
CMD ["python", "main.py"] 