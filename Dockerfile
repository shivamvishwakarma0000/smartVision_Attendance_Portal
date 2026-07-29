FROM python:3.10-slim

# Install system dependencies required by dlib, face_recognition, OpenCV
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pre-compiled binary wheel for dlib to prevent slow C++ compilation timeouts
RUN pip install --no-cache-dir dlib-bin || true

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

# Create required directories
RUN mkdir -p uploads/faces temp_uploads instance

# Expose both 8080 (Runsite platform standard) and 7860 (Hugging Face fallback)
EXPOSE 8080 7860

ENV PORT=8080
ENV HOST=0.0.0.0

# Use 1 worker with 2 threads for optimal memory footprint (<200MB) on 256MB RAM instances
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 2 --timeout 120 app:app"]
