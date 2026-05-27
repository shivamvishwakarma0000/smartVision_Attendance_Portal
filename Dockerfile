# Use a python slim base image
FROM python:3.10-slim-bullseye

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    MAKEFLAGS="-j1" \
    MAX_JOBS="1" \
    CFLAGS="--param ggc-min-expand=1 --param ggc-min-heapsize=32768" \
    CXXFLAGS="--param ggc-min-expand=1 --param ggc-min-heapsize=32768"

# Set work directory
WORKDIR /app

# Install system dependencies required for CMake, Dlib, and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Expose port (Hugging Face Spaces uses 7860, Render overrides via PORT env)
EXPOSE 7860

# Start app using Gunicorn with multi-threading to prevent locks during face scans
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "app:app", "--threads", "4", "--workers", "1", "--timeout", "120"]
