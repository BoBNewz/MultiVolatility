FROM debian

# Install system dependencies (matches working Dockerfile-test exactly)
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-dev \
    gcc \
    wget \
    make \
    libusb-1.0-0-dev \
    && rm -rf /var/lib/apt/lists/*

# Download the pre-compiled MemProcFS/LeechCore C-libraries based on architecture
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "arm64" ]; then \
    URL="https://github.com/ufrisk/MemProcFS/releases/download/v5.17/MemProcFS_files_and_binaries_v5.17.2-linux_aarch64-20260224.tar.gz"; \
    else \
    URL="https://github.com/ufrisk/MemProcFS/releases/download/v5.17/MemProcFS_files_and_binaries_v5.17.2-linux_x64-20260224.tar.gz"; \
    fi && \
    wget "$URL" -O memprocfs.tar.gz && \
    tar -xzvf memprocfs.tar.gz && \
    cp vmm.so /usr/lib/ && \
    cp leechcore.so /usr/lib/ && \
    rm -rf memprocfs.tar.gz vmm.so leechcore.so

# Install Python packages
RUN pip install --break-system-packages --no-cache-dir memprocfs flask

WORKDIR /app

# Copy the sidecar server
COPY memprocfs_server.py .

EXPOSE 5002
CMD ["python3", "memprocfs_server.py"]
