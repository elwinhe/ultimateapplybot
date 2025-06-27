########################  base-image  ########################
FROM python:3.12-slim AS base-image

# Set environment variables for Python and uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/root/.local/bin:$PATH"

# Install system dependencies required for building some Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv, the fast Python package installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app

########################  python-dependencies (Production) ########################
FROM base-image as python-dependencies

# Copy only the dependency manifest first to leverage Docker layer caching
COPY pyproject.toml ./

# Install only the main project dependencies using uv
# This layer is only rebuilt when pyproject.toml changes
RUN uv pip install --system --no-cache .


########################  api-runtime (Final Production Image)  ########################
FROM python-dependencies AS api-runtime

# Copy the application code from the current directory into the container
COPY ./app ./app

# Create a non-root user, change ownership for the app directory, and then switch to the user
RUN adduser --disabled-password --gecos "" app && chown -R app:app /app
USER app

EXPOSE 8000

# Define a healthcheck for the API service
HEALTHCHECK CMD ["curl", "-f", "http://localhost:8000/healthcheck"]

# The command to run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


########################  test-runtime (Final Test Image)  ########################
FROM api-runtime AS test-runtime

# The api-runtime image uses the 'app' user. Switch back to root
# to install development packages.
USER root

# Copy the dependency manifest again to install dev dependencies.
COPY pyproject.toml ./
# This layer is only rebuilt when pyproject.toml changes.
RUN uv pip install --system --no-cache ".[dev]"

# Copy the tests directory into the image.
COPY ./tests ./tests

# Switch back to the non-root user for running the tests.
USER app

# The default command for this stage is to run the test suite.
CMD ["pytest", "-q", "tests/"]