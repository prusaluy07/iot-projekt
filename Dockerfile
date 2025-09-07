FROM python:3.11-slim

# System-Updates und curl installieren
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis setzen
WORKDIR /app

# Requirements kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code kopieren
COPY app/ .

# Port freigeben
EXPOSE 8000
EXPOSE 8001

# App starten
CMD ["python", "main.py"]
