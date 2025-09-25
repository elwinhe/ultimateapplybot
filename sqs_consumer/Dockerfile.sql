FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies including asyncpg
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir asyncpg

# Copy application code
COPY . .

# Run the SQL version of the consumer
CMD ["python", "consumer_sql.py"]
