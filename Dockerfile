FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/ai_orchestrator/storage

EXPOSE 8400

CMD ["uvicorn", "ai_orchestrator.server:app", "--host", "0.0.0.0", "--port", "8400"]
