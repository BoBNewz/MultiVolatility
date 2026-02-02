#!/bin/bash

docker buildx build --platform linux/amd64,linux/arm64 -t sp00kyskelet0n/volatility3:latest --push .
