# Data Service — documents, chunking, uploads.
# No ML dependencies, so this image stays small.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY services/data_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py            ./services/__init__.py
COPY services/common/                ./services/common/
COPY services/data_service/          ./services/data_service/

# Bundled knowledge-base documents ship inside the image; uploads go to a volume.
COPY backend/finance_kb/             ./finance_kb/

ENV KB_DIR=/app/finance_kb \
    UPLOAD_DIR=/data/uploaded_kb

RUN mkdir -p /data/uploaded_kb

EXPOSE 8003

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8003/health',timeout=4)" || exit 1

CMD ["uvicorn", "services.data_service.main:app", "--host", "0.0.0.0", "--port", "8003"]
