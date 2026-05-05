FROM python:3.11-slim

# Dependencias para PostgreSQL y herramientas de compilación para Chroma
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalamos las librerías necesarias para el cerebro de la agencia
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ajustamos el PYTHONPATH para tu estructura específica
ENV PYTHONPATH="/app/chatbox/src"

# Ejecutamos la app
CMD ["python", "chatbox/src/app.py"]