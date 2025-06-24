########################  python-runtime  ########################
FROM python:3.12-slim AS api-runtime

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

# Copy only the dependency manifest first to leverage Docker cache
COPY pyproject.toml ./

# Install project dependencies using uv
# This layer is only rebuilt when pyproject.toml changes
RUN uv pip install --system --no-cache .

# Copy the application code
COPY ./app ./app

# Drop root privileges for security
RUN adduser --disabled-password --gecos "" app
USER app

EXPOSE 8000

# Use the more robust array/exec form for CMD
HEALTHCHECK CMD ["curl", "-f", "http://localhost:8000/healthcheck"]

# Use array form for CMD to avoid shell processing
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]