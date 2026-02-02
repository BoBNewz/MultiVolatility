FROM debian:trixie-slim

RUN apt update && apt install -y \
    git \
    python3 \
    python3-pip \
    make \
    gcc \
    python3-dev \
    libusb-dev \
    libusb-1.0-0-dev \
    libusb-1.0-0 pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/volatilityfoundation/volatility3.git && \
    cd volatility3 && \
    pip install --break-system-packages pyarrow && \
    pip install --break-system-packages -e ".[full]"

WORKDIR /volatility3