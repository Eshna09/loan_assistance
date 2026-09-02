# LLM Service — thin wrapper around the Ollama runtime.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1

COPY services/llm_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/__init__.py            ./services/__init__.py
COPY services/common/                ./services/common/
COPY services/llm_service/           ./services/llm_service/

ENV OLLAMA_URL=http://ollama:11434     OLLAMA_MODEL=codellama:7b

EXPOSE 8002

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=5     CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8002/health',timeout=4)" || exit 1

CMD ["uvicorn", "services.llm_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
