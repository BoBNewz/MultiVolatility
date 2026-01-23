FROM python:3.9-slim

WORKDIR /app

ENV STORAGE_DIR=/storage

# Install system dependencies if any (we might need gcc for some python packages, but trying slim first)
# Volatility usage inside is via Docker SDK, so we don't need vol2/vol3 deps here, 
# just the MultiVol CLI deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create cache/symbol directories to ensure they exist
RUN mkdir -p volatility2_profiles volatility3_symbols volatility3_plugins volatility3_cache

ENTRYPOINT ["python", "main.py", "--api"]
