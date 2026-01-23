# MultiVolatility

MultiVolatility uses multi-processing to run volatility2 and volatility3 docker containers.
The tool comes with the possibility to send JSON outputs to a web application.

## Build docker images

```shell
git clone https://github.com/BoBNewz/MultiVolatility.git
cd MultiVolatility
docker build Dockerfiles/volatility2/ -t volatility2
docker build Dockerfiles/volatility3/ -t volatility3
```

## Send outputs to the web application

Modify the URL and the API password in the config.yml.

![MultiVolatility](https://github.com/user-attachments/assets/f77c636d-b647-4218-9617-20268616689c)
