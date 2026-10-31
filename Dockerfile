FROM python:3.11-slim

# Install system packages: Tesseract OCR, English model, Poppler utilities, libgl for OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency specifications first for Docker layer caching
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire application codebase
COPY . .

# Set environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_ENV=production \
    STORAGE_BACKEND=db \
    ML_MODE=inprocess

EXPOSE 8000

# Start single-worker Uvicorn bound to dynamic Render $PORT
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
