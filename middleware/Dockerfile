FROM python:3.11-slim

WORKDIR /app

# System-Tools installieren (curl, nodejs, npm)
RUN apt-get update && apt-get install -y \
    curl \
    nodejs \
    npm \
 && rm -rf /var/lib/apt/lists/*

# Python-Requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY middleware.py .

# Optional: wscat global installieren
RUN npm install -g wscat

CMD ["uvicorn", "middleware:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
