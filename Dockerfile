# Official Python image use karenge
FROM python:3.11-slim

# Server ke andar ek /app folder banayenge
WORKDIR /app

# Requirements file ko server mein copy karo
COPY requirements.txt .

# Saare packages install karo
RUN pip install --no-cache-dir -r requirements.txt

# Ab apna baaki saara code copy karo
COPY . .

# FastAPI ka default port open karo
EXPOSE 8000

# Server start karne ki command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]