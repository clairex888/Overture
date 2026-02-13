FROM python:3.11-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

ENV PORT=8000
CMD uvicorn src.main:app --host 0.0.0.0 --port $PORT
