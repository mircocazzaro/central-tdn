import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('-dzyj5_ndx2xn7#4-mvxbuxc^2g!=pelj!0l7s$-emri3cog^$', 'unsafe-dev-key')
#DEBUG = os.getenv('DEBUG', 'False') == 'True'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'catalogapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',       # ← fixed
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',                  # if you need CSRF
    'django.contrib.auth.middleware.AuthenticationMiddleware',    # for auth
    'django.contrib.messages.middleware.MessageMiddleware',
]

ROOT_URLCONF = 'centralproject.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'catalogapp' / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            # …
            'django.contrib.messages.context_processors.messages',
        ],
    },
}]



WSGI_APPLICATION = 'centralproject.wsgi.application'

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_ROOT = BASE_DIR / 'data'
os.makedirs(MEDIA_ROOT, exist_ok=True)

# Path to your catalog of allowed SPARQL templates (create via your existing node)
ALLOWED_DB   = os.path.join(MEDIA_ROOT, 'allowed_queries.duckdb')
# Central’s own endpoints list
ENDPOINTS_DB = os.path.join(MEDIA_ROOT, 'endpoints.duckdb')


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Simple manager password (in real life use env var!)
ENDPOINT_MANAGER_PASSWORD = 'supersecret'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]