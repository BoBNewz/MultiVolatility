FROM python:3.13

# Install system dependencies and clone repo
RUN apt update && \
    apt install -y libusb-1.0-0-dev git && \
    git clone https://github.com/volatilityfoundation/volatility3.git && \
    python3 -m venv /volatility3/venv && \
    /volatility3/venv/bin/pip install -e "/volatility3[dev]" && \
    ln -s /volatility3/vol.py /usr/local/bin/vol && \
    chmod +x /volatility3/vol.py && \
    apt clean && rm -rf /var/lib/apt/lists/*

COPY keepass.py /volatility3/volatility3/plugins/keepass.py

# Use the virtual environment by default
ENV PATH="/volatility3/venv/bin:$PATH"
ENV VIRTUAL_ENV="/volatility3/venv"
ENV PYTHONWARNINGS=ignore

WORKDIR /volatility3

CMD ["vol"]
