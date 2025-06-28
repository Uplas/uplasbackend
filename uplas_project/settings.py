# uplas_project/settings.py
"""
Django settings for uplas_project project.
"""

import os
from pathlib import Path
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
import dotenv

# --- Base Configuration ---
BASE_DIR = Path(__file__).resolve().parent.parent
dotenv.load_dotenv(BASE_DIR / '.env') # Load .env file if it exists

# --- Security & Core Settings ---
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-fallback-key-for-dev')
DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS_STRING = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',') if host.strip()]

CSRF_TRUSTED_ORIGINS_STRING = os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in CSRF_TRUSTED_ORIGINS_STRING.split(',') if origin.strip()]

# --- Application Definition ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    'storages', # Ensure 'storages' is always in INSTALLED_APPS when using GCS
    'whitenoise.runserver_nostatic', # For development with WhiteNoise (optional)
    'whitenoise', # Required for WhiteNoise production serving

    # Your apps
    'apps.core.apps.CoreConfig',
    'apps.users.apps.UsersConfig',
    'apps.courses.apps.CoursesConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.projects.apps.ProjectsConfig',
    'apps.community.apps.CommunityConfig',
    'apps.blog.apps.BlogConfig',
    'apps.ai_agents.apps.AiAgentsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoiseMiddleware should be placed directly after Django's SecurityMiddleware
    'whitenoise.middleware.WhiteNoiseMiddleware', # ADDED/MOVED for static file serving
    'corsheaders.middleware.CorsMiddleware', # Needs to be high up, esp. before CommonMiddleware
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'uplas_project.urls'
WSGI_APPLICATION = 'uplas_project.wsgi.application'
ASGI_APPLICATION = 'uplas_project.asgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# --- Database ---
DB_ENGINE = os.environ.get('DB_ENGINE', 'django.db.backends.mysql')
DB_NAME = os.environ.get('DB_NAME', 'uplas_dev_db')
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_PORT = os.environ.get('DB_PORT', '3306')

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': DB_NAME,
        'USER': DB_USER,
        'PASSWORD': DB_PASSWORD,
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}
# --- Cloud SQL Socket Path (Production) ---
# If deploying to App Engine or Cloud Run in the same region as Cloud SQL, use Unix Sockets
INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
if not DEBUG and INSTANCE_CONNECTION_NAME:
    DATABASES['default']['HOST'] = f'/cloudsql/{INSTANCE_CONNECTION_NAME}'
    DATABASES['default']['PORT'] = ''  # Must be empty for Unix sockets

# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = os.environ.get('DJANGO_LANGUAGE_CODE', 'en-us')
LANGUAGES = [ ('en', _('English')), ('es', _('Spanish')), ('fr', _('French')), ]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = os.environ.get('DJANGO_TIME_ZONE', 'Africa/Nairobi')
USE_I18N = True
USE_L10N = True
USE_TZ = True

# --- Static & Media Files ---
# IMPORTANT: Since GCS bucket is not public, Django will serve these files.
# STATIC_URL and MEDIA_URL should be relative paths.
STATIC_URL = '/static/'
MEDIA_URL = '/media/'

GS_BUCKET_NAME = os.environ.get('GS_BUCKET_NAME')

if not DEBUG and GS_BUCKET_NAME:
    # 'storages' app should be in INSTALLED_APPS unconditionally when used in production
    # or ensure it's explicitly added if not already. Moved 'storages' to the main list.
    # We still want to use GCS as the storage backend, even if Django serves them.
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
            "OPTIONS": {
                "bucket_name": GS_BUCKET_NAME,
                "location": "media",
                "default_acl": "projectPrivate", # Ensure files are not publicly accessible by default
            }
        },
        "staticfiles": {
            "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
            "OPTIONS": {
                "bucket_name": GS_BUCKET_NAME,
                "location": "static",
                "default_acl": "projectPrivate", # Ensure files are not publicly accessible by default
            }
        },
    }
    # When serving via Django + WhiteNoise, STATIC_ROOT is where collectstatic will place files
    # before WhiteNoise serves them (or before django-storages pushes them to GCS).
    # WhiteNoise will then handle serving from this location (or directly from GCS via Django-storages
    # for media, and also for static if WhiteNoise is configured for that).
    STATIC_ROOT = BASE_DIR / 'staticfiles_collected' # Define a path for collected static files
    # WhiteNoise will serve from this STATIC_ROOT.
    # Django-storages will handle MEDIA_ROOT for media files.
    MEDIA_ROOT = BASE_DIR / 'mediafiles_dev' # This path is for dev, but in prod, files go to GCS

    # WhiteNoise configuration for production.
    # It will automatically find files in STATIC_ROOT.
    # Note: Ensure `collectstatic` is run during your build process.
    # To use WhiteNoise, ensure `STATIC_ROOT` is properly defined for collectstatic.
    # WhiteNoise serves files directly from STATIC_ROOT.
    #
    # Important: The URLs below are now relative, letting Django handle them.
    # The GCS backend still *stores* the files, but the server pulls them.
    # STATIC_URL and MEDIA_URL remain relative so your Django app can handle routing.
else:
    # If DEBUG is True or GS_BUCKET_NAME is not set, use local file paths
    STATIC_ROOT = BASE_DIR / 'staticfiles_collected'
    MEDIA_ROOT = BASE_DIR / 'mediafiles_dev'


# --- Defaults & Custom User Model ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'users.User'

# --- Django REST Framework ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.IsAuthenticatedOrReadOnly',],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': int(os.environ.get('DRF_PAGE_SIZE', 10)),
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer',]
}
if DEBUG: REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'].append('rest_framework.renderers.BrowsableAPIRenderer')

# --- Simple JWT ---
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.environ.get('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.environ.get('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 7))),
    'ROTATE_REFRESH_TOKENS': True, 'BLACKLIST_AFTER_ROTATION': True, 'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256', 'SIGNING_KEY': SECRET_KEY, 'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id', 'USER_ID_CLAIM': 'user_id',
}

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get('DJANGO_CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',') if origin.strip()]
CORS_ALLOW_CREDENTIALS = True

# --- Email ---
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = os.environ.get('DJANGO_EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
    EMAIL_HOST = os.environ.get('DJANGO_EMAIL_HOST')
    EMAIL_PORT = int(os.environ.get('DJANGO_EMAIL_PORT', 587))
    EMAIL_USE_TLS = os.environ.get('DJANGO_EMAIL_USE_TLS', 'True').lower() == 'true'
    EMAIL_HOST_USER = os.environ.get('DJANGO_EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = os.environ.get('DJANGO_EMAIL_HOST_PASSWORD')
    DEFAULT_FROM_EMAIL = os.environ.get('DJANGO_DEFAULT_FROM_EMAIL', 'UPLAS Platform <noreply@uplas.me>')

# --- Logging ---
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '{levelname} {asctime} {module} {message}', 'style': '{',}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'simple',}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {'django': {'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False,}},
}

# --- Custom App Settings ---
SITE_NAME = "UPLAS Platform"
DEFAULT_CURRENCY = 'USD'
CURRENCY_CHOICES = [ ('USD', _('US Dollar')), ('EUR', _('Euro')), ('KES', _('Kenyan Shilling')), ]
WHATSAPP_CODE_EXPIRY_MINUTES = int(os.environ.get('WHATSAPP_CODE_EXPIRY_MINUTES', 10))

# --- Stripe ---
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

# --- AI Agent Service URLs ---
AI_NLP_TUTOR_SERVICE_URL = os.environ.get('AI_NLP_TUTOR_SERVICE_URL')
AI_TTS_SERVICE_URL = os.environ.get('AI_TTS_SERVICE_URL')
AI_TTV_SERVICE_URL = os.environ.get('AI_TTV_SERVICE_URL')
AI_PROJECT_GENERATOR_SERVICE_URL = os.environ.get('AI_PROJECT_GENERATOR_SERVICE_URL')
AI_PROJECT_ASSESSMENT_SERVICE_URL = os.environ.get('AI_PROJECT_ASSESSMENT_SERVICE_URL')
AI_SERVICE_API_KEY = os.environ.get('AI_SERVICE_API_KEY')

# --- Production Security Settings ---
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'True').lower() == 'true'
    SESSION_COOKIE_SECURE = os.environ.get('DJANGO_SESSION_COOKIE_SECURE', 'True').lower() == 'true'
    CSRF_COOKIE_SECURE = os.environ.get('DJANGO_CSRF_COOKIE_SECURE', 'True').lower() == 'true'
    # Consider HSTS settings carefully:
    # SECURE_HSTS_SECONDS = 31536000 # 1 year
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # SECURE_HSTS_PRELOAD = True
