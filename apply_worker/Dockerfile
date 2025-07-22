# Use the official Playwright image which includes all browser dependencies
FROM mcr.microsoft.com/playwright/python:v1.53.0-jammy

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt using uv
# The Playwright image already has pip, so we can install uv
RUN pip install uv
RUN uv pip install --no-cache-dir --system -r requirements.txt

# The browsers are already installed in this base image, so 'playwright install' is not needed.

# Copy the rest of the application's code into the container
COPY . .

# Command to run the application
CMD ["python", "main.py"] 