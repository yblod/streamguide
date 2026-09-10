ARG BUILD_FROM=ghcr.io/home-assistant/aarch64-base-python:3.13-alpine3.22
FROM ${BUILD_FROM}

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMGUIDE_DATA_DIR=/data

WORKDIR /opt/streamguide
RUN mkdir -p /data

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY run.py config.yaml ./
COPY app ./app
COPY static ./static

EXPOSE 8765

CMD ["python3", "/opt/streamguide/run.py"]
