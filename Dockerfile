# Dockerfile
# --- Base Stage ---
# Use an official Python runtime as a base image
FROM python:3.9-slim-bullseye AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies needed for mysqlclient and potentially Pillow
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \ # Even if using MySQL, often useful for other tools or potential future use
       default-libmysqlclient-dev \ # For mysqlclient
       gcc \
       pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# --- Builder Stage ---
# This stage installs Python dependencies
FROM base AS builder

# Install build tools
RUN pip install --upgrade pip setuptools wheel

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
# Using --no-cache-dir reduces image size
# Using a virtual environment is good practice, though less critical in a final container image
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt
RUN pip install --no-cache /app/wheels/*

# --- Final Stage ---
# This stage builds the final production image
FROM base AS final

# Copy the installed dependencies from the builder stage
COPY --from=builder /usr/local/lib/python3.9/site-packages/ /usr/local/lib/python3.9/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy the application code
COPY . .

# --- Gunicorn Setup ---
# Gunicorn is a popular WSGI server for running Django in production.
# Ensure Gunicorn is in your requirements.txt.
# We'll use a gunicorn.conf.py file for configuration (create this file).
COPY gunicorn.conf.py /app/gunicorn.conf.py

# --- Static Files (Optional - if NOT serving static from GCS/CDN directly) ---
# If you are serving static files via GCS, you typically don't run collectstatic here.
# If using GCS for storage but want Gunicorn/Whitenoise to handle /static/ (less common on Cloud Run),
# you might run it. For GCS, usually you upload during build/deploy.
# We'll assume GCS handles static/media and skip collectstatic here for a cleaner Cloud Run setup.
# If you need it:
# RUN python manage.py collectstatic --noinput

# Expose the port Gunicorn will run on
EXPOSE 8000

# Command to run the application using Gunicorn
# Ensure 'uplas_project.wsgi:application' points correctly to your WSGI app.
CMD ["gunicorn", "--conf", "gunicorn.conf.py", "uplas_project.wsgi:application"]
