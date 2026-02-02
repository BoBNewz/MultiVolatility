FROM debian:bullseye-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    python2 \
    python2.7-minimal \
    ca-certificates \
    git \
    build-essential \
    make \
    wget \
    gcc \
    python2-dev \
    libusb-dev \
    libusb-1.0-0-dev \
    libusb-1.0-0 pkg-config \
    pcregrep \
    libpcre++-dev \
    python-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/* && \
    wget -O /tmp/get-pip.py https://bootstrap.pypa.io/pip/2.7/get-pip.py && \
    python2 /tmp/get-pip.py

RUN pip install yara-python pycryptodome distorm3

RUN git clone https://github.com/volatilityfoundation/volatility.git && \
    cd volatility && \
    python2 setup.py install
