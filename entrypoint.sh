#!/bin/bash
# entrypoint.sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run Django migrations
echo "Running Django migrations..."
python manage.py migrate --noinput

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn uplas_project.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 90