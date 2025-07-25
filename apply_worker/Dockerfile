# Use the official Playwright image which includes all browser dependencies
FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

# Install xvfb and a VNC server
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends xvfb x11vnc fluxbox && \
    rm -rf /var/lib/apt/lists/*

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

# Copy the entrypoint script
COPY entrypoint.sh .

# Make the script executable
RUN chmod +x entrypoint.sh

# Set the entrypoint to our script
ENTRYPOINT ["./entrypoint.sh"] 