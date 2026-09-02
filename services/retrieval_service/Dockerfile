# Retrieval / RAG Service — MiniLM embeddings + FAISS index.
# The heavy image: torch, sentence-transformers, faiss.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models

COPY services/retrieval_service/requirements.txt ./requirements.txt

# CPU-only torch keeps the image at a fraction of the CUDA build's size.
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.2.2 \
 && pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image so container start needs no network
# and every run embeds with byte-identical weights.
RUN python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

COPY services/__init__.py            ./services/__init__.py
COPY services/common/                ./services/common/
COPY services/retrieval_service/     ./services/retrieval_service/

ENV DATA_SERVICE_URL=http://data-service:8003

EXPOSE 8001

HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=5 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8001/health',timeout=4)" || exit 1

CMD ["uvicorn", "services.retrieval_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
