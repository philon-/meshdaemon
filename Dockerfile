FROM python:3.13-slim-bookworm

# Prevent Python from writing bytecode and buffering output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies for UDP multicast support
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy application code
COPY app ./app

# Create non-root user for security
# Note: multicast socket operations work fine as non-root user
RUN useradd --create-home --uid 10001 meshdaemon \
    && chown -R meshdaemon:meshdaemon /app

USER meshdaemon

ENTRYPOINT ["python", "-m", "app.main"]
