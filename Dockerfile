# Dockerfile for uplas.me-backend
# This Dockerfile builds the Django backend application for deployment on Cloud Run.

# --- Base Stage ---
    FROM python:3.11-slim-bookworm AS base
    ENV PYTHONDONTWRITEBYTECODE 1
    ENV PYTHONUNBUFFERED 1
    ENV APP_HOME /app
    WORKDIR $APP_HOME
    RUN apt-get update \
        && apt-get install -y --no-install-recommends \
           build-essential \
           default-libmysqlclient-dev \
           gcc \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*
    
    # --- Builder Stage ---
    FROM base AS builder
    RUN pip install --upgrade pip
    COPY requirements.txt .
    RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt
    
    # --- Final Stage ---
    FROM base AS final
    COPY --from=builder /app/wheels /app/wheels
    RUN pip install --no-cache-dir /app/wheels/*
    COPY . .
    RUN python manage.py collectstatic --noinput
    
    # Add and make the entrypoint script executable
    COPY entrypoint.sh .
    RUN chmod +x ./entrypoint.sh
    
    EXPOSE 8000
    
    # Set the entrypoint to our script
    ENTRYPOINT ["./entrypoint.sh"]