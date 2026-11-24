FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pytest

# Copy application files
COPY . .

# Expose server port
EXPOSE 8000

# Start FastAPI server
CMD ["python", "-c", "import uvicorn; uvicorn.run('server:api', host='0.0.0.0', port=8000)"]
