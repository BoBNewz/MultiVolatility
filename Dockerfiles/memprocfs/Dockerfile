FROM debian

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-dev \
    gcc \
    wget \
    make \
    libusb-1.0-0-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_BREAK_SYSTEM_PACKAGES=1
# Download MemProcFS/LeechCore C-libraries based on architecture
RUN ARCH=$(uname -m) && \
    if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then \
    URL="https://github.com/ufrisk/MemProcFS/releases/download/v5.17/MemProcFS_files_and_binaries_v5.17.3-linux_aarch64-20260301.tar.gz"; \
    else \
    URL="https://github.com/ufrisk/MemProcFS/releases/download/v5.17/MemProcFS_files_and_binaries_v5.17.3-linux_x64-20260301.tar.gz"; \
    fi && \
    wget "$URL" -O memprocfs.tar.gz && \
    tar -xzvf memprocfs.tar.gz && \
    cp vmm.so /usr/lib/ && \
    cp leechcore.so /usr/lib/ && \
    rm -rf memprocfs.tar.gz vmm.so leechcore.so

RUN uv pip install --system --no-cache memprocfs flask gunicorn

WORKDIR /app

COPY memprocfs_server.py .

EXPOSE 5002
# Single worker is mandatory — the VMM session state lives in-process.
# Threads handle concurrent health polls while a dump is loading.
# Timeout is long to accommodate /list which can take several minutes on large dumps.
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--worker-class", "gthread", \
    "--timeout", "600", "--bind", "0.0.0.0:5002", "memprocfs_server:app"]
