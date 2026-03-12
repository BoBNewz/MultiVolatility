FROM python:3.13-slim

WORKDIR /app

ENV STORAGE_DIR=/app/storage/data
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy requirements
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy source code
COPY . .

# Create cache/symbol directories to ensure they exist
RUN mkdir -p volatility2_profiles volatility3_symbols volatility3_plugins volatility3_cache

ENTRYPOINT ["python", "-m", "multivol.multivol", "--api"]
