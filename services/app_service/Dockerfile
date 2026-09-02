# Application / Orchestration Service — the public API gateway.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1

COPY services/app_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py            ./services/__init__.py
COPY services/common/                ./services/common/
COPY services/app_service/           ./services/app_service/

ENV DATA_SERVICE_URL=http://data-service:8003     RETRIEVAL_SERVICE_URL=http://retrieval-service:8001     LLM_SERVICE_URL=http://llm-service:8002

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5     CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/',timeout=4)" || exit 1

CMD ["uvicorn", "services.app_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
