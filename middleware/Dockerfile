# Basisimage
FROM python:3.11-slim

# Arbeitsverzeichnis
WORKDIR /app

# Abhängigkeiten kopieren
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Middleware-Code kopieren
COPY . /app

# Port freigeben
EXPOSE 8080

# Startbefehl
CMD ["uvicorn", "middleware:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
