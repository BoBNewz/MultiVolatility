# This Dockerfile is not optimized with a ton of RUN statements. This is for easier debugging
FROM accenturecifr/volatility3

RUN apk add git curl gcc musl-dev linux-headers python3-dev

RUN git clone https://github.com/spitfirerxf/vol3-plugins.git && \
    git clone https://github.com/kudelskisecurity/volatility-gpg.git && \
    git clone https://github.com/fox-it/OpenSSH-Session-Key-Recovery.git 

ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.1
RUN python3 -m pip install --use-pep517 cryptography stream_sqlite --break-system-packages
RUN cd OpenSSH-Session-Key-Recovery && cd pip-package && python3 setup.py install
RUN cp vol3-plugins/* /opt/volatility3/volatility3/framework/plugins/windows
RUN cp volatility-gpg/linux/* /opt/volatility3/volatility3/framework/plugins/linux
RUN curl https://raw.githubusercontent.com/fox-it/OpenSSH-Session-Key-Recovery/main/volatility3/openssh_sessionkeys.py --output /opt/volatility3/volatility3/framework/plugins/linux/openssh_sessionkeys.py
