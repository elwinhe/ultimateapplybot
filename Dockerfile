########################  base-image  ########################
FROM python:3.12-slim AS base-image

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Set path for uv to be accessible
    PATH="/root/.local/bin:$PATH"

# Install system dependencies required for building some Python packages
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv directly, which is faster than using pip
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

WORKDIR /app

########################  python-dependencies  ########################
FROM base-image as python-dependencies

# Copy only the dependency manifest first to leverage Docker cache
COPY pyproject.toml ./

# Install project dependencies using uv
# This layer is only rebuilt when pyproject.toml changes
RUN uv pip install --system --no-cache .


########################  api-runtime (Production Image)  ########################
FROM python-dependencies AS api-runtime

# Copy the application code
COPY ./app ./app

# Drop root privileges for security
RUN adduser --disabled-password --gecos "" app
USER app

EXPOSE 8000
HEALTHCHECK CMD ["curl", "-f", "http://localhost:8000/healthcheck"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


########################  test-runtime (Test Image)  ########################
# ADD THIS NEW STAGE
# This stage builds on the production image and adds dev dependencies.
FROM api-runtime AS test-runtime

# Switch back to root to install dev packages
USER root

# Install the optional [dev] dependencies from pyproject.toml
RUN uv pip install --system --no-cache ".[dev]"

# Switch back to the non-root user for running tests
USER app

# The default command for this stage will be to run pytest
CMD ["pytest"]
