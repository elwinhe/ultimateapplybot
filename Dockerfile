########################  python-runtime  ########################
FROM python:3.12-slim AS api-runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# system deps 
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# pip → uv
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir uv

WORKDIR /app

# dependency manifests
COPY requirements.txt pyproject.toml ./
RUN uv pip install --system --no-cache-dir -r requirements.txt

# application code 
COPY ./app ./app
RUN uv pip install --system --no-cache-dir .

# drop privileges
RUN adduser --disabled-password --gecos "" app
USER app

EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/healthcheck || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
