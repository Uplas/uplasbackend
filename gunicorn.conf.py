# gunicorn.conf.py
import os

# Number of Gunicorn worker processes.
# Cloud Run typically works well with 1 worker per vCPU, but start with a reasonable number like 2-4.
# Use an environment variable or a default.
workers = int(os.environ.get('GUNICORN_WORKERS', '3'))

# Number of threads per worker.
threads = int(os.environ.get('GUNICORN_THREADS', '1'))

# The address and port to bind to.
# For Cloud Run, use 0.0.0.0 and the port specified by the $PORT env var (default 8080, but 8000 is common for Django).
# Cloud Run automatically injects $PORT, but 8000 is a safe bet if $PORT isn't set.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# Timeout for workers (in seconds).
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))

# Log level.
loglevel = os.environ.get('GUNICORN_LOGLEVEL', 'info')

# Where to log access and error logs. ' - ' means stdout/stderr, suitable for Cloud Run Logging.
accesslog = '-'
errorlog = '-'

# Set Gunicorn to run in the foreground (required for container environments).
daemon = False

# WSGI application path.
# Should match what's in your CMD in Dockerfile, but can be set here too.
# chdir = '/app' # Ensure we are in the right directory
# module = 'uplas_project.wsgi:application'

# Worker class (sync is default, but gevent or uvicorn might be needed for async/websockets)
# worker_class = 'sync'
