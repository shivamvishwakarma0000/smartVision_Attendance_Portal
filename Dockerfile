# Use a lightweight miniconda base image to install precompiled dlib without source compilation
FROM continuumio/miniconda3:latest

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies required for OpenCV/GUI libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install pre-compiled dlib from conda-forge (prevents GCC OOM compilation errors)
RUN conda install -y -c conda-forge dlib && conda clean -afy

# Copy and install python dependencies via pip
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Expose port (Hugging Face Spaces uses 7860, Render overrides via PORT env)
EXPOSE 7860

# Start app using Gunicorn with multi-threading to prevent locks during face scans
CMD ["gunicorn", "--bind", "0.0.0.0:7860", "app:app", "--threads", "4", "--workers", "1", "--timeout", "120"]

