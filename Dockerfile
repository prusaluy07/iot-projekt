FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY middleware.py .

CMD ["uvicorn", "middleware:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
