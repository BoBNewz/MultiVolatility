# This Dockerfile is not optimized with a ton of RUN statements. This is for easier debugging
FROM accenturecifr/volatility3

RUN apk add git curl gcc musl-dev linux-headers python3-dev

RUN git clone https://github.com/spitfirerxf/vol3-plugins.git && \
    git clone https://github.com/kudelskisecurity/volatility-gpg.git && \
    git clone https://github.com/fox-it/OpenSSH-Session-Key-Recovery.git 

ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.1
RUN python3 -m pip install --use-pep517 cryptography stream_sqlite
RUN cd OpenSSH-Session-Key-Recovery && cd pip-package && python3 setup.py install
RUN cp vol3-plugins/* /usr/lib/python3.10/site-packages/volatility3-2.11.0-py3.10.egg/volatility3/framework/plugins/windows
RUN cp volatility-gpg/linux/* /usr/lib/python3.10/site-packages/volatility3-2.11.0-py3.10.egg/volatility3/framework/plugins/linux
RUN curl https://raw.githubusercontent.com/fox-it/OpenSSH-Session-Key-Recovery/main/volatility3/openssh_sessionkeys.py --output /usr/lib/python3.10/site-packages/volatility3-2.11.0-py3.10.egg/volatility3/framework/plugins/linux/openssh_sessionkeys.py
