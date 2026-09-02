@echo off
REM ============================================================
REM  Loan Knowledge Assistance - all four services, no Docker
REM ============================================================
REM  Each service runs in its own window so you can see its logs
REM  and stop one independently.
REM
REM    data-service       :8003   documents, chunking, uploads
REM    retrieval-service  :8001   MiniLM embeddings + FAISS
REM    llm-service        :8002   Ollama / Code Llama
REM    app-service        :8000   orchestration + public API
REM
REM  Ollama must already be running:  ollama serve
REM ============================================================

cd /d "%~dp0"

echo Starting Data Service on :8003 ...
start "data-service :8003" cmd /k python -m uvicorn services.data_service.main:app --host 127.0.0.1 --port 8003

echo Starting Retrieval Service on :8001 ...
start "retrieval-service :8001" cmd /k python -m uvicorn services.retrieval_service.main:app --host 127.0.0.1 --port 8001

echo Starting LLM Service on :8002 ...
start "llm-service :8002" cmd /k python -m uvicorn services.llm_service.main:app --host 127.0.0.1 --port 8002

echo Starting Application Service on :8000 ...
start "app-service :8000" cmd /k python -m uvicorn services.app_service.main:app --host 127.0.0.1 --port 8000

echo.
echo All four services launching. The Retrieval Service takes ~20s to load MiniLM.
echo.
echo   Aggregate health:  http://localhost:8000/health
echo   API docs:          http://localhost:8000/docs
echo   Dashboard:         run start_frontend.bat, then http://localhost:5173
echo.
pause
