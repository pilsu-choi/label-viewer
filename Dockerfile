FROM python:3.12-slim

RUN groupadd -r labelviewer && useradd -r -g labelviewer -d /app labelviewer

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/ scripts/

ENV LABEL_VIEWER_DATA=/data
RUN mkdir -p /data && chown -R labelviewer:labelviewer /data /app

USER labelviewer
EXPOSE 8765

CMD ["python", "-m", "backend.app", "--data", "/data", "--host", "0.0.0.0", "--port", "8765"]
