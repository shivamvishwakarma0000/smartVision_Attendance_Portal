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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create required directories
RUN mkdir -p uploads/faces temp_uploads instance

# Expose Hugging Face default port 7860
EXPOSE 7860

ENV PORT=7860
ENV HOST=0.0.0.0

CMD ["gunicorn", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "120", "app:app"]
