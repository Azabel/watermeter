ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:bookworm
FROM ${BUILD_FROM}

# Tesseract para la verificación OCR de los rodillos. Debian (glibc) en lugar
# de Alpine porque las ruedas de opencv/numpy son manylinux.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-pip tesseract-ocr tesseract-ocr-eng tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config/calibration.json ./config/calibration.json
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir ".[ocr]"

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
