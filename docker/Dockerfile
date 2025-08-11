FROM python:3.11-slim

#ENV PYTHONDONTWRITEBYTECODE=1 \
#    PYTHONUNBUFFERED=1 \
#    HF_HOME=/app/.cache/hf \
#    TRANSFORMERS_CACHE=/app/.cache/hf \
#    TORCH_HOME=/app/.cache/torch

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/.cache/hf \
    HUGGINGFACE_HUB_CACHE=/app/.cache/hf \
    TORCH_HOME=/app/.cache/torch

# Paquetes del sistema (OCR, PDF, utilidades)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-spa poppler-utils curl tini git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requisitos Python (sin Torch)
COPY docker/requirements.txt /app/docker/requirements.txt
RUN pip install --no-cache-dir -r /app/docker/requirements.txt

# PyTorch con CUDA para la 3090 (CUDA 12.1). Si prefieres cu118, cambia el index-url.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu121 \
    torch torchvision torchaudio

# Código y entrypoint
COPY app /app/app
COPY config /app/config
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Directorios de datos (los montas por volumen)
RUN mkdir -p /app/data /app/output

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["/app/entrypoint.sh"]
