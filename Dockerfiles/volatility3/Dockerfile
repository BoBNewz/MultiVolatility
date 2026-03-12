FROM debian:trixie-slim

RUN apt update && apt install -y \
    git \
    python3 \
    python3-dev \
    make \
    gcc \
    libusb-dev \
    libusb-1.0-0-dev \
    libusb-1.0-0 pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_BREAK_SYSTEM_PACKAGES=1

RUN git clone https://github.com/volatilityfoundation/volatility3.git && \
    cd volatility3 && \
    uv pip install --system --no-cache pyarrow && \
    uv pip install --system --no-cache -e ".[full]"

WORKDIR /volatility3