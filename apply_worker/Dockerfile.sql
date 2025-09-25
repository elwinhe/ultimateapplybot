FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app

# Install additional dependencies
RUN apt-get update && apt-get install -y \
    x11vnc \
    xvfb \
    fluxbox \
    wget \
    wmctrl \
    && rm -rf /var/lib/apt/lists/*

# Set up VNC
ENV DISPLAY=:99
RUN mkdir ~/.vnc && x11vnc -storepasswd 1234 ~/.vnc/passwd

# Copy requirements
COPY requirements.txt .

# Install Python dependencies including asyncpg
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir asyncpg

# Copy application code
COPY . .

# Create entrypoint for SQL version
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "worker_sql.py"]
