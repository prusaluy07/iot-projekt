FROM python:3.11-slim

# System-Updates und benötigte Tools installieren
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnisse setzen
WORKDIR /app

# Requirements kopieren (falls lokal vorhanden)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt || true

# Ports freigeben
EXPOSE 8000
EXPOSE 8001

# Startkommando: Repo aktualisieren und App starten
ENTRYPOINT ["/bin/sh", "-c", "\
  if [ ! -d /src/.git ]; then \
    git clone --depth=1 https://github.com/prusaluy07/iot-projekt.git /src; \
  else \
    cd /src && git pull; \
  fi && \
  cp -r /src/* /app/ && \
  python /app/main.py \
"]
