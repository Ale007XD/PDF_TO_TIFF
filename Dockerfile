# Dockerfile
FROM python:3.10-slim

WORKDIR /bot

RUN apt-get update \
    && apt-get install -y imagemagick ghostscript icc-profiles nginx python3-venv python3-pip file \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python3 -m venv .venv
RUN ./.venv/bin/pip install --upgrade pip && ./.venv/bin/pip install -r requirements.txt

COPY . .

CMD ["./.venv/bin/python", "main.py"]
