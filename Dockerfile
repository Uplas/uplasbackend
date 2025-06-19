# Dockerfile for uplas.me-backend
# This Dockerfile builds the Django backend application for deployment on Cloud Run.

# --- Base Stage ---
# Use an official Python runtime as a base image, updated to 3.11 slim 'bookworm'
FROM python:3.11-slim-bookworm AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV APP_HOME /app
WORKDIR $APP_HOME

# Install system dependencies needed for mysqlclient and other tools.
# 'libpq-dev' is for PostgreSQL, 'default-libmysqlclient-dev' for MySQL. Keep both for flexibility.
# 'build-essential', 'gcc', 'pkg-config' are for compiling Python packages with C extensions.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
       default-libmysqlclient-dev \
       gcc \
       pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Builder Stage ---
# This stage installs Python dependencies using pip wheel to optimize layers
FROM base AS builder

# Install build tools for pip
RUN pip install --upgrade pip setuptools wheel

# Copy requirements file to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies into /app/wheels
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Install the dependencies from the wheels
RUN pip install --no-cache /app/wheels/*

# --- Final Stage ---
# This stage builds the final production image
FROM base AS final

# Copy the installed Python dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy the application code
COPY . .

# --- Static Files Collection ---
# Run collectstatic to prepare static files for WhiteNoise/GCS.
# This should happen *before* the application starts and before the image is finalized.
RUN python manage.py collectstatic --noinput

# --- Gunicorn Setup ---
# Gunicorn is a popular WSGI server for running Django in production.
# Ensure Gunicorn is in your requirements.txt.
# We'll use command-line arguments for configuration directly.
# Expose the port Gunicorn will run on (Cloud Run provides this via the PORT env var)
EXPOSE 8000

# Command to run the application using Gunicorn
# --bind 0.0.0.0:${PORT} is crucial for Cloud Run, which assigns the PORT dynamically.
# --workers: Adjust based on your Cloud Run instance's CPU (e.g., 2-4 workers per CPU core).
# --timeout: Set a reasonable timeout for requests.
CMD exec gunicorn uplas_project.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 90
