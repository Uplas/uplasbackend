
# uplas_backend/uplas_project/settings.py

# Add 'apps.users' and other apps to INSTALLED_APPS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders', # For Cross-Origin Resource Sharing

    'apps.users',
    'apps.courses',
    'apps.payments',
    'apps.projects',
    'apps.community',
    'apps.blog',
    'apps.ai_agents', # Generic app for AI related views/urls if not in courses/projects directly
    'apps.core',
]

AUTH_USER_MODEL = 'users.User' # Use our custom user model

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly', # Default to read-only for unauthenticated
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10 
}

# Configure Simple JWT (adjust lifetimes as needed)
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60), # e.g., 1 hour
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),    # e.g., 7 days
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

# CORS settings (configure appropriately for your frontend URL)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000", # Example for local frontend development if any
    "http://127.0.0.1:3000",
    "https://your-frontend-domain.com", # Your deployed frontend domain
    "https://*.uplas.me", # Allow subdomains if frontend is hosted there
]
CORS_ALLOW_CREDENTIALS = True # If you use session-based auth or cookies for CSRF

# Internationalization (already in default Django settings, ensure it's configured) 
LANGUAGE_CODE = 'en-us' # Default language
LANGUAGES = [
    ('en', _('English')),
    ('es', _('Español')),
    ('fr', _('Français')),
]
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]
TIME_ZONE = 'Africa/Nairobi' # Set to your primary timezone
USE_I18N = True
USE_L10N = True # For localized formatting of dates, numbers, etc.
USE_TZ = True

# Database (will be configured via environment variables for Cloud SQL) 
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'uplas_db'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'), # For Cloud SQL Proxy: 127.0.0.1, For direct: Cloud SQL IP
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'", # MySQL strict mode
            'charset': 'utf8mb4',
        },
    }
}
# Add Google Cloud Storage for static and media files when deploying
# Example (you'll need django-storages and google-cloud-storage libraries):
# if not DEBUG:
#     DEFAULT_FILE_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
#     STATICFILES_STORAGE = 'storages.backends.gcloud.GoogleCloudStorage'
#     GS_BUCKET_NAME = os.environ.get('GS_BUCKET_NAME')
#     GS_DEFAULT_ACL = 'publicRead' # Or private and serve via signed URLs
#     # GS_PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT')
#
#     MEDIA_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/media/'
#     STATIC_URL = f'https://storage.googleapis.com/{GS_BUCKET_NAME}/static/'
#     MEDIA_ROOT = '' # Not used with GCS
#     STATIC_ROOT = '' # Not used with GCS
# else:
#     STATIC_URL = '/static/'
#     STATIC_ROOT = BASE_DIR / 'staticfiles_collected'
#     MEDIA_URL = '/media/'
#     MEDIA_ROOT = BASE_DIR / 'mediafiles'


# Email Backend (configure for transactional emails like verification, password reset)
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = os.environ.get('EMAIL_HOST')
# EMAIL_PORT = os.environ.get('EMAIL_PORT', 587)
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
# EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
# DEFAULT_FROM_EMAIL = 'Uplas Support <support@uplas.com>'
