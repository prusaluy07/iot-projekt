FROM python:3.11-slim

# System-Updates und benötigte Tools installieren
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis setzen
WORKDIR /app

# Requirements kopieren (falls im Repo vorhanden) und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

# Optional: Ports freigeben
EXPOSE 8000
EXPOSE 8001

# Bei Containerstart: Repo ziehen/aktualisieren und App starten
ENTRYPOINT ["/bin/sh", "-c", "\
  if [ ! -d /app/.git ]; then \
    git clone --depth=1 https://github.com/prusaluy07/iot-projekt.git /app; \
  else \
    cd /app && git pull; \
  fi && \
  python main.py \
"]
